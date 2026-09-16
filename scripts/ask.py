#!/usr/bin/env python
"""Ask one question of your own, on whichever arm you want to ask it on.

Every other entry point in this repository answers questions from
`data/golden/` — the frozen set the evaluation is measured on. That is the
right constraint for a figure and the wrong one for a person with an actual
rules dispute, and until now the only code path that answered free text was
`scripts/bootstrap.py`, which hardcodes one question.

**The stack is `run_eval.py`'s, not a second copy of it.** `build_retrieval_stack`
and `retrieve_one` are imported, so what answers here is the code that produced
the published numbers, configured by the same `plan_arm`. A demo with its own
retrieval path is a demo that can drift from the thing it is demonstrating —
and this harness has already shipped a run labelled arm B that was arm C.

**Which arm to ask on is a real choice, and the default is not always right.**
Arm C is the shipped hybrid and the default. It enters through entity linking:
a question naming a card or a keyword gets a traversal from it, and a question
resolving neither returns `no_entities` without ever reaching text retrieval,
because the planner returns before that branch. Arm A has no linker to fail.

Two questions asked through this script hit that outcome immediately, for two
different reasons, and only one of them is a limitation rather than a defect.
"Does damage carry over between turns?" names nothing to link, which is the
boundary of a card-seeded design. "Gollum, Riddle Master's ability" names a card
that is **in the graph** and does not match, because the lexicon holds exact
names and the possessive is not one; "the ability of Gollum, Riddle Master"
resolves it and retrieves the ruling that answers the question. Measured on the
frozen splits, the possessive costs one resolved entity on 3 of the 57
evaluation questions and 1 of the 20 development questions, and turned none of
them seedless — those questions name other things too. It is fatal only when
the apostrophe lands on the only entity in the sentence.

**Read the refusals as output, not as breakage.** `CANNOT ANSWER` means the
retrieved context did not contain the rule, and the pipeline says so instead of
letting the model write from thirty years of Magic it happens to remember.

**The incompleteness notice is ON, unlike in E-001.** Pin 11 suppresses it on
every arm because a passage retriever truncating at *k* cannot emit one, and
handing the graph arms an invitation to hedge that the baseline never receives
would bias the comparison being run. That argument is about fairness between
arms. A person reading an answer is not an arm, and should be told when the
context was trimmed.

Usage:
    python scripts/ask.py "Can I respond to a creature's ETB trigger?"
    python scripts/ask.py "..." --arm A                 # no linker to fail
    python scripts/ask.py "..." --retrieval-only        # free: no model call
    python scripts/ask.py "..." --show-context          # the prompt as sent
    python scripts/ask.py "..." --text tfidf            # C's registered ablation
"""

from __future__ import annotations

import argparse
import re
import sys
from contextlib import ExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from graphrag_mtg.config import get_settings
from graphrag_mtg.extraction.llm import LlmClient, estimate_cost
from graphrag_mtg.generation.answerer import (
    FAN_CONTENT_NOTICE,
    PROMPT_VERSION,
    SYSTEM,
    answer,
    build_prompt,
    prompt_digest,
    refusal_reason,
)
from graphrag_mtg.retrieval.subgraph import (
    DEFAULT_KIND_CAP,
    DEFAULT_TOKEN_BUDGET,
    Outcome,
    Subgraph,
    serialize,
)
from run_e007 import MAX_ANSWER_TOKENS
from run_eval import (
    ARMS,
    CR_TXT_PATH,
    DEFAULT_EMBEDDING_MODEL,
    RULINGS_PATH,
    VECTORS_PATH,
    build_retrieval_stack,
    plan_arm,
    require_a_populated_graph,
    retrieve_one,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

#: Evidence lines printed before the answer. Enough to see what the arm
#: reached and by which edge; `--show-context` prints all of it.
PREVIEW = 8

#: An English possessive on a card name. `QueryLinker` matches surfaces
#: against a lexicon of exact card names, and "Gollum, Riddle Master's ability"
#: does not contain one — the same question with "the ability of Gollum, Riddle
#: Master" resolves the card and retrieves the ruling that answers it.
POSSESSIVE = re.compile(r"\w's\b")

#: What to suggest when linking resolves nothing. Named here rather than
#: written into the message, because the advice is only correct while arm A
#: has no linker in front of it — if that changes, this constant is the
#: single place the suggestion lives.
SEEDLESS_HINT = (
    "Nothing in the question resolved to a card or a keyword, so arm C had "
    "nothing to traverse from and the planner returned before text retrieval "
    "(--always-text cannot reach past this). Try --arm A, which searches the "
    "corpus and has no linker to fail."
)

#: Added when the question carries a possessive, because then the reader has
#: probably named a card and watched it not resolve, and "ask arm A instead"
#: would send them away from the arm that can actually answer them.
POSSESSIVE_HINT = (
    "This question contains \"'s\". The lexicon holds exact card names, so "
    "\"<Card>'s ability\" does not match while \"the ability of <Card>\" does. "
    "If you named a card, try rephrasing it that way first — arm C may answer "
    "it fully."
)


def hint_for(subgraph: Subgraph, arm: str) -> str | None:
    """The one refusal a reader should be told how to get past.

    `NO_ENTITIES` fired **zero** times across E-001's 57 evaluation questions
    and appeared on the first two questions asked outside them. That is what a
    golden set drawn from a card-question site looks like from the other side,
    and the two questions failed for different reasons — one named no card at
    all, one named a card and put an apostrophe after it. Sending the second
    reader to arm A would move them off the arm that answers them.

    Every other outcome is a genuine limit and gets no advice. Offering a flag
    on `no_seed` or `no_match` would teach a reader to re-roll until the output
    looks better, which is the habit this project spent eleven phases not
    building.

    The question is read off the subgraph rather than passed in beside it.
    `Subgraph.question` is already the question verbatim, and a second copy is
    a second thing that can be wrong — the first version of this took both, and
    a caller passing only the subgraph got advice chosen from an empty string
    with nothing to say it had happened.
    """
    if subgraph.outcome is not Outcome.NO_ENTITIES or arm == "A":
        return None
    if POSSESSIVE.search(subgraph.question):
        return f"{POSSESSIVE_HINT}\n\n{SEEDLESS_HINT}"
    return SEEDLESS_HINT


def needs_encoder(args: argparse.Namespace) -> bool:
    """Whether this configuration will embed the question.

    The documents are cached and the question is not, so `hybrid` and `dense`
    cost one embedding call per ask on any arm whose retriever is the vector
    one — arm A always, arm C when its text half is the shipped vector version.
    """
    plan = plan_arm(args)
    return plan.retriever == "vector" and args.mode in {"hybrid", "dense"}


def preflight(args: argparse.Namespace) -> None:
    """Fail before the expensive part, not after it.

    Building the corpus takes about two minutes and 115,547 documents, and
    discovering a missing key afterwards is two minutes spent to be told
    something knowable at once.
    """
    settings = get_settings()
    if needs_encoder(args) and not settings.openai_api_key:
        raise SystemExit(
            f"--mode {args.mode} embeds your question, and no OPENAI_API_KEY is "
            "configured.\n"
            "  --mode lexical   the same retriever, BM25 half only, no key needed\n"
            "  --text tfidf     arm C's registered TF-IDF ablation, no key needed"
        )
    if needs_encoder(args) and not args.vectors.exists():
        # `bootstrap.py` builds the graph and says, correctly, that the vector
        # index is a separate ~20-minute paid build. So the default
        # configuration is exactly the one a reader who followed the quickstart
        # cannot run yet, and finding that out after the corpus build is two
        # minutes spent to be told something this line already knows.
        raise SystemExit(
            f"No vector index at {args.vectors}, and this configuration needs one.\n"
            "  python scripts/run_eval.py index   builds it (paid, ~20 min, prints "
            "an estimate first)\n"
            "  --mode lexical                     BM25 over the same corpus, free\n"
            "  --text tfidf                       arm C's TF-IDF ablation, free"
        )
    if not args.retrieval_only and not (settings.anthropic_api_key or settings.openai_api_key):
        raise SystemExit(
            "No LLM key configured, so nothing can be generated. "
            "Pass --retrieval-only to see the evidence retrieval reaches, which "
            "needs no credentials at all."
        )
    if not args.cr.exists():
        raise SystemExit(f"No Comprehensive Rules at {args.cr}. Run scripts/bootstrap.py first.")


def report_retrieval(subgraph: Subgraph, *, show_context: bool) -> None:
    """What the arm reached, and by which edge.

    The path is printed beside every item on purpose. It is the one thing the
    graph arm has that the vector baseline does not — E-029 measured the vector
    arm's provenance as a single constant string across 2,215 items — and it is
    what makes an answer checkable rather than merely confident.
    """
    kinds = sorted({item.kind for item in subgraph.evidence})
    counts = ", ".join(
        f"{kind} {sum(1 for e in subgraph.evidence if e.kind == kind)}" for kind in kinds
    )
    print(f"outcome:   {subgraph.outcome}" + (f" — {subgraph.note}" if subgraph.note else ""))
    print(f"evidence:  {len(subgraph.evidence)} item(s)" + (f" ({counts})" if counts else ""))
    print(f"templates: {', '.join(subgraph.templates_run) or 'none ran'}")
    if subgraph.dropped or subgraph.capped:
        print(f"trimmed:   dropped {dict(subgraph.dropped)}, capped {dict(subgraph.capped)}")
    if show_context:
        print("\n--- context as sent ---")
        print(serialize(subgraph))
        print("--- end of context ---")
        return
    for item in subgraph.evidence[:PREVIEW]:
        print(f"  [{item.cite()}] {item.text[:110]}")
        print(f"      via {item.template}: {item.path}")
    if len(subgraph.evidence) > PREVIEW:
        print(f"  ... {len(subgraph.evidence) - PREVIEW} more (--show-context for all)")


def build_parser() -> argparse.ArgumentParser:
    """The command line, separated from running it.

    Which arm the defaults select is a decision, and a decision that can only
    be exercised by building a 115,547-document corpus is a decision whose test
    gets skipped. `run_eval.py` isolates `plan_arm` for the same reason, after
    a run went out labelled arm B while it was arm C.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="the rules question, in quotes")
    parser.add_argument(
        "--arm",
        choices=sorted(ARMS),
        default="C",
        help="; ".join(f"{name}: {what}" for name, what in sorted(ARMS.items())),
    )
    parser.add_argument(
        "--text",
        choices=("vector", "tfidf"),
        default="vector",
        help="arm C's text half: the shipped retriever, or its registered ablation",
    )
    parser.add_argument("--mode", choices=("hybrid", "dense", "lexical"), default="hybrid")
    parser.add_argument("--always-text", action="store_true", help="E-001's ablation of the router")
    parser.add_argument("--iterative", action="store_true", help="pin 13's protocol variable")
    parser.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    parser.add_argument("--kind-cap", type=int, default=DEFAULT_KIND_CAP)
    parser.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    parser.add_argument("--rulings", type=Path, default=RULINGS_PATH)
    parser.add_argument("--vectors", type=Path, default=VECTORS_PATH)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--model", default=None, help="defaults to LLM_MODEL in .env")
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="show the evidence; send nothing, spend nothing",
    )
    parser.add_argument(
        "--show-context", action="store_true", help="print the serialized context in full"
    )
    parser.add_argument("--dry-run", action="store_true", help="print the estimate, send nothing")
    # `build_retrieval_stack` reads both. Neither belongs on this command line:
    # `--cards` exists for the CI fixture, and a smoke run answers with a fake
    # generator, which is the one thing a person asking a real question does
    # not want.
    parser.set_defaults(cards=None, smoke=False)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    preflight(args)

    with ExitStack() as resources:
        stack = build_retrieval_stack(args, resources)
        require_a_populated_graph(stack)
        subgraph = retrieve_one(args.question, stack, args)

    print(f"question:  {args.question}")
    print(f"arm {args.arm} — {ARMS[args.arm]}")
    report_retrieval(subgraph, show_context=args.show_context)

    if subgraph.outcome is not Outcome.RESOLVED or subgraph.is_empty:
        # The model is never called here, which is the whole point: asking it to
        # write about an empty page is precisely when it writes from memory.
        print(f"\nNo generation: {refusal_reason(subgraph)}")
        hint = hint_for(subgraph, args.arm)
        if hint:
            print(f"\n{hint}")
        return 0
    if args.retrieval_only:
        print("\nRetrieval only: nothing was sent.")
        return 0

    prompt = build_prompt(args.question, subgraph)
    client = LlmClient(model=args.model, max_tokens=MAX_ANSWER_TOKENS, temperature=0.0)
    estimate = estimate_cost(
        [prompt], model=client.model, output_tokens_per_call=MAX_ANSWER_TOKENS, system=SYSTEM
    )
    print(f"\nmodel {client.model} @ temperature 0, prompt {PROMPT_VERSION}")
    print(f"estimate: {estimate}")
    print(f"prompt sha256: {prompt_digest(SYSTEM, prompt)}")
    if args.dry_run:
        print("\nDry run: nothing was sent.")
        return 0

    result = answer(
        args.question,
        subgraph,
        lambda system, sent: client.complete_text(sent, system=system),
        model=client.model,
    )
    print()
    print(result.rendered or result.text)
    if result.unknown:
        # Every entry is a citation to something the context does not contain.
        # Mechanically detected, and the one line here that means the answer is
        # unsound regardless of how well it reads.
        print(f"\nFABRICATED CITATIONS: {', '.join(result.unknown)}")
    print(f"\n---\n{FAN_CONTENT_NOTICE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
