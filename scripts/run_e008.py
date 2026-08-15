#!/usr/bin/env python
"""E-008: does the model answer from the graph, or from what it already knows?

Every grounding claim in this project rests on an assumption that is false
by default — that the answer came from the retrieved subgraph. Magic is
thirty years old with an enormous public corpus, and the model knows it, so
a correct answer is **not** evidence of grounding. E-007 cannot separate the
two: a well-cited answer produced from memory passes every check it makes.

So the graph is made to say something the world does not, and the answer is
read against the graph rather than against Magic.

    load      fictional constructs into the live graph, counted
    verify    retrieve per probe and check the fiction actually arrived
    generate  one answer per probe (paid)
    code      four outcomes, judged against a discriminator written first
    report    the registered rule, applied
    teardown  delete every fixture node, and prove none is left

The order matters in one place above all: **`graph_says` and `memory_says`
are authored in the fixture before any answer exists.** Deciding after the
fact what would have counted as a leak is how this experiment would measure
nothing.

Namespace hygiene is a property, not a name prefix. Every fictional node
carries `fixture: 'e008'` and is deleted by it. Prefixed *names* were
rejected deliberately: they announce the fiction to the model, and a model
that spots the fake and refuses is coded as a grounding failure — the
detector would be measuring itself.

Usage:
    python scripts/run_e008.py load
    python scripts/run_e008.py verify
    python scripts/run_e008.py generate --split dev --dry-run
    python scripts/run_e008.py code --next
    python scripts/run_e008.py report
    python scripts/run_e008.py teardown
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

from graphrag_mtg.etl.cr_parser import CR_TXT_PATH
from graphrag_mtg.extraction.llm import LlmClient, estimate_cost
from graphrag_mtg.generation.answerer import PROMPT_VERSION, SYSTEM, answer, build_prompt
from graphrag_mtg.graph.connection import driver_session
from graphrag_mtg.retrieval.pipeline import neo4j_runner, retrieve
from graphrag_mtg.retrieval.subgraph import DEFAULT_KIND_CAP, DEFAULT_TOKEN_BUDGET, serialize

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_e007 import MAX_ANSWER_TOKENS, build_stack

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FIXTURE_PATH = Path("data/fixtures/e008_constructs.json")
RETRIEVAL_PATH = Path("runs/e008_retrieval.jsonl")
ANSWERS_PATH = Path("runs/e008_answers.jsonl")
CODING_PATH = Path("data/golden/e008_coding.jsonl")

#: Marks every node and relationship this experiment creates. Teardown
#: deletes by this and nothing else, and `verify --clean` proves it worked.
TAG = "e008"

#: Registered before the first probe: zero leaks, and the graph followed on
#: at least this share of probes whose evidence was verified present. The
#: second condition is what stops a run that refuses everything from being
#: reported as clean.
FOLLOW_FLOOR = 0.80

OUTCOMES = ("followed_graph", "leak", "refused", "intra_context_conflict")

CODING_CRIB = """\
  followed_graph          the answer follows what the loaded graph says
  leak                    it contradicts the graph in favour of real Magic
  refused                 refusal or hedge, on a probe whose evidence was
                          verified present — a grounding failure, not a pass
  intra_context_conflict  it follows one loaded item against another (oracle
                          text against the injected ruling, say). Following
                          the subgraph, so never a leak.

  Judge against `graph says` below, which was written before any answer
  existed. A right-by-accident answer is coded on its reasoning: if the
  sentence agrees with the graph for a reason the graph does not give, it
  did not follow the graph."""

RULE = "-" * 78


def wrap(text: str) -> str:
    return textwrap.fill(text, width=76, initial_indent="  ", subsequent_indent="  ")


def load_fixture(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"No fixture at {path}.")
    return json.loads(path.read_text(encoding="utf-8"))


def probes(fixture: dict, split: str) -> list[dict]:
    rows = fixture["probes"]
    return rows if split == "all" else [p for p in rows if p["split"] == split]


def counts(session) -> dict[str, int]:
    """Node and relationship totals, and how many carry the fixture tag."""
    return {
        "nodes": session.run("MATCH (n) RETURN count(n) AS n").single()["n"],
        "rels": session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"],
        "fixture_nodes": session.run(
            f"MATCH (n {{fixture: '{TAG}'}}) RETURN count(n) AS n"
        ).single()["n"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Load and teardown — counted, never asserted
# ─────────────────────────────────────────────────────────────────────────────


def collisions(session, fixture: dict) -> list[str]:
    """Fixture keys that already name a node in the production graph.

    The check that was missing, and its absence destroyed real data. `MERGE`
    on an existing key does not create — it *adopts*, stamping the fictional
    text and the fixture tag onto a real node, which teardown then deletes
    by that tag. Rule 702.184 is the real keyword *Station*; loading a
    fictional 702.184 overwrote it and tearing down removed it, along with
    702.184a and 702.184b.
    """
    found: list[str] = []
    for card in fixture["cards"]:
        if session.run(
            "MATCH (c:Card {normalized_name: $n}) RETURN count(c) AS n",
            n=card["normalized_name"],
        ).single()["n"]:
            found.append(f"Card {card['name']}")
    for keyword in fixture["keywords"]:
        if session.run(
            "MATCH (k:Keyword {name: $n}) RETURN count(k) AS n", n=keyword["name"]
        ).single()["n"]:
            found.append(f"Keyword {keyword['display_name']}")
    for rule in fixture["rules"]:
        if session.run(
            "MATCH (r:Rule {number: $n}) RETURN count(r) AS n", n=rule["number"]
        ).single()["n"]:
            found.append(f"Rule {rule['number']}")
    for ruling in fixture["rulings"]:
        if session.run(
            "MATCH (r:Ruling {ruling_id: $n}) RETURN count(r) AS n", n=ruling["ruling_id"]
        ).single()["n"]:
            found.append(f"Ruling {ruling['ruling_id']}")
    return found


def load(args: argparse.Namespace) -> int:
    """Create the fictional constructs, and refuse if the graph is dirty."""
    fixture = load_fixture(args.fixture)
    with driver_session() as session:
        before = counts(session)
        if before["fixture_nodes"] and not args.force:
            raise SystemExit(
                f"{before['fixture_nodes']} fixture node(s) already present. Run "
                "`teardown` first — loading twice leaves a graph nobody can describe."
            )
        clashes = collisions(session, fixture)
        if clashes:
            raise SystemExit(
                "These fixture keys already exist in the production graph:\n  "
                + "\n  ".join(clashes)
                + "\n\nLoading would adopt those nodes rather than create new ones, and "
                "teardown would then delete real data. Choose keys the corpus does not "
                "hold. This check exists because that already happened once: a fictional "
                "702.184 overwrote the real keyword Station and teardown removed it."
            )

        for card in fixture["cards"]:
            session.run(
                "MERGE (c:Card {oracle_id: $oracle_id}) "
                "SET c.name = $name, c.normalized_name = $normalized_name, "
                "    c.oracle_text = $oracle_text, c.type_line = $type_line, c.fixture = $tag",
                tag=TAG,
                **{k: card[k] for k in
                   ("oracle_id", "name", "normalized_name", "oracle_text", "type_line")},
            )
        for keyword in fixture["keywords"]:
            session.run(
                "MERGE (k:Keyword {name: $name}) "
                "SET k.display_name = $display_name, k.glossary_text = $glossary_text, "
                "    k.fixture = $tag",
                tag=TAG,
                **{k: keyword[k] for k in ("name", "display_name", "glossary_text")},
            )
        for rule in fixture["rules"]:
            session.run(
                "MERGE (r:Rule {number: $number}) "
                "SET r.text = $text, r.level = $level, r.fixture = $tag",
                tag=TAG,
                **{k: rule[k] for k in ("number", "text", "level")},
            )
        for rule in fixture["rules"]:
            if rule.get("parent"):
                session.run(
                    "MATCH (p:Rule {number: $parent}), (c:Rule {number: $number}) "
                    "MERGE (p)-[e:HAS_SUBRULE]->(c) SET e.fixture = $tag",
                    tag=TAG, parent=rule["parent"], number=rule["number"],
                )
        for keyword in fixture["keywords"]:
            session.run(
                "MATCH (k:Keyword {name: $name}), (r:Rule {number: $rule_number}) "
                "MERGE (k)-[e:DEFINED_BY]->(r) SET e.fixture = $tag",
                tag=TAG, name=keyword["name"], rule_number=keyword["rule_number"],
            )
        for card in fixture["cards"]:
            for name in card.get("keywords", []):
                session.run(
                    "MATCH (c:Card {oracle_id: $oracle_id}), (k:Keyword {display_name: $display}) "
                    "MERGE (c)-[e:HAS_KEYWORD]->(k) SET e.fixture = $tag",
                    tag=TAG, oracle_id=card["oracle_id"], display=name,
                )

        missing: list[str] = []
        for ruling in fixture["rulings"]:
            # Construct 3 attaches to a *real* card, which is the only place
            # this experiment touches production data. The card node is not
            # modified; a tagged Ruling and a tagged edge are added and both
            # are removed by teardown.
            found = session.run(
                "MATCH (c:Card {normalized_name: $card}) RETURN count(c) AS n", card=ruling["card"]
            ).single()["n"]
            if not found:
                missing.append(ruling["card"])
                continue
            session.run(
                "MERGE (r:Ruling {ruling_id: $ruling_id}) "
                "SET r.text = $text, r.published_at = $published_at, r.fixture = $tag "
                "WITH r MATCH (c:Card {normalized_name: $card}) "
                "MERGE (c)-[e:HAS_RULING]->(r) SET e.fixture = $tag",
                tag=TAG,
                **{k: ruling[k] for k in ("ruling_id", "text", "published_at", "card")},
            )
        after = counts(session)

    expected = len(fixture["cards"]) + len(fixture["keywords"]) + len(fixture["rules"])
    expected += len(fixture["rulings"])
    created = after["nodes"] - before["nodes"]
    print(f"before   nodes {before['nodes']}  rels {before['rels']}")
    print(f"after    nodes {after['nodes']}  rels {after['rels']}")
    print(f"fixture nodes now {after['fixture_nodes']}   created {created}, expected {expected}")
    if created != expected or after["fixture_nodes"] != expected:
        raise SystemExit(
            f"Expected to create {expected} node(s); the graph grew by {created} and carries "
            f"{after['fixture_nodes']} tagged. A tagged node this load did not create is a "
            "real node about to be deleted by teardown."
        )
    if missing:
        raise SystemExit(
            f"Real card(s) not in the graph: {', '.join(missing)}. The fictional-ruling "
            "construct has nothing to attach to, which is a fixture defect and must be "
            "fixed before generating rather than reported as a result."
        )
    print("Next: python scripts/run_e008.py verify")
    return 0


def teardown(args: argparse.Namespace) -> int:
    """Delete every tagged node and edge, then prove none remains."""
    with driver_session() as session:
        before = counts(session)
        session.run(f"MATCH ()-[e {{fixture: '{TAG}'}}]-() DELETE e")
        session.run(f"MATCH (n {{fixture: '{TAG}'}}) DETACH DELETE n")
        after = counts(session)

    print(f"before   nodes {before['nodes']}  rels {before['rels']}  fixture {before['fixture_nodes']}")
    print(f"after    nodes {after['nodes']}  rels {after['rels']}  fixture {after['fixture_nodes']}")
    if after["fixture_nodes"]:
        raise SystemExit(
            f"{after['fixture_nodes']} fixture node(s) survived teardown. Nothing else may "
            "run against this database until that is zero."
        )
    print("Clean. The fictional constructs are gone.")
    return 0


def verify_clean(args: argparse.Namespace) -> int:
    """Assert the production graph holds nothing of this experiment's."""
    with driver_session() as session:
        present = counts(session)["fixture_nodes"]
    print(f"fixture nodes present: {present}")
    if present:
        raise SystemExit("The graph is not clean. Run `teardown` before any production run.")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Verify — the fiction has to arrive before an answer can be judged
# ─────────────────────────────────────────────────────────────────────────────


def verify(args: argparse.Namespace) -> int:
    """Retrieve for every probe and record whether its evidence is present.

    A probe whose subgraph lacks the fiction it asks about is a **retrieval
    miss**, excluded from the leak denominator and reported. Without this
    the prompt would be iterated against a retrieval defect, and E-006's
    first run — 0.067, both causes harness bugs — is why that is not a
    hypothetical.
    """
    fixture = load_fixture(args.fixture)
    linker, searcher, oracle_text = build_stack(
        args.cr,
        extra_cards=fixture["cards"],
        extra_keywords=[k["display_name"] for k in fixture["keywords"]],
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    misses: list[str] = []
    with driver_session() as session, args.out.open("w", encoding="utf-8") as handle:
        run = neo4j_runner(session)
        for probe in probes(fixture, args.split):
            subgraph = retrieve(
                probe["question"],
                linker=linker,
                run=run,
                rule_search=searcher,
                oracle_text=oracle_text,
                token_budget=args.token_budget,
                kind_cap=args.kind_cap,
            )
            keys = {f"{item.kind}:{item.key}" for item in subgraph.evidence}
            absent = [need for need in probe["needs"] if need not in keys]
            if absent:
                misses.append(f"{probe['id']} ({', '.join(absent)})")
            handle.write(
                json.dumps(
                    {
                        "probe_id": probe["id"],
                        "construct": probe["construct"],
                        "split": probe["split"],
                        "question": probe["question"],
                        "outcome": str(subgraph.outcome),
                        "templates_run": subgraph.templates_run,
                        "evidence_keys": sorted(keys),
                        "needs": probe["needs"],
                        "evidence_present": not absent,
                        "missing": absent,
                        "dropped": dict(subgraph.dropped),
                        "capped": dict(subgraph.capped),
                        "context": serialize(subgraph),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    total = len(probes(fixture, args.split))
    print(f"Verified {total} probe(s) -> {args.out}")
    print(f"evidence present: {total - len(misses)}/{total}")
    if misses:
        print("RETRIEVAL MISSES — excluded from the leak denominator, and reported:")
        for miss in misses:
            print(f"  {miss}")
        print("A miss is a fixture or retrieval defect. Fix it before generating if you can;")
        print("if it stands, it is reported as a miss and never as a leak.")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Generate — paid, and only against verified retrieval
# ─────────────────────────────────────────────────────────────────────────────


def generate(args: argparse.Namespace) -> int:
    """One answer per probe, at temperature 0, against the loaded fiction."""
    if not args.retrieval.exists():
        raise SystemExit(f"No verification at {args.retrieval}. Run `verify` first.")
    records = [
        json.loads(line)
        for line in args.retrieval.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.split != "all":
        records = [r for r in records if r["split"] == args.split]
    if args.limit:
        records = records[: args.limit]
    if not records:
        raise SystemExit("Nothing to generate.")

    out = args.out or ANSWERS_PATH.with_name(f"e008_answers_{args.split}.jsonl")
    if out.exists() and not args.force:
        raise SystemExit(f"{out} already exists — pass --force only if you mean to replace it.")

    fixture = load_fixture(args.fixture)
    linker, searcher, oracle_text = build_stack(
        args.cr,
        extra_cards=fixture["cards"],
        extra_keywords=[k["display_name"] for k in fixture["keywords"]],
    )
    client = LlmClient(model=args.model, max_tokens=MAX_ANSWER_TOKENS, temperature=0.0)

    with driver_session() as session:
        run = neo4j_runner(session)
        prepared = [
            (
                record,
                retrieve(
                    record["question"],
                    linker=linker,
                    run=run,
                    rule_search=searcher,
                    oracle_text=oracle_text,
                    token_budget=args.token_budget,
                    kind_cap=args.kind_cap,
                ),
            )
            for record in records
        ]
        prompts = [build_prompt(r["question"], s) for r, s in prepared]
        estimate = estimate_cost(
            prompts, model=client.model, output_tokens_per_call=MAX_ANSWER_TOKENS, system=SYSTEM
        )
        print(f"model {client.model} @ temperature 0, prompt {PROMPT_VERSION}")
        print(f"estimate: {estimate}")
        if args.dry_run:
            print("\nDry run: nothing was sent.")
            return 0

        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            for record, subgraph in prepared:
                result = answer(
                    record["question"],
                    subgraph,
                    lambda system, prompt: client.complete_text(prompt, system=system),
                )
                handle.write(
                    json.dumps(
                        {
                            "probe_id": record["probe_id"],
                            "construct": record["construct"],
                            "split": record["split"],
                            "question": record["question"],
                            "text": result.text,
                            "rendered": result.rendered,
                            "refused": result.refused,
                            "generated": result.generated,
                            "evidence_present": record["evidence_present"],
                            "prompt_version": result.prompt_version,
                            "model": client.model,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                print(f"  {record['probe_id']}: {'refused' if result.refused else 'answered'}")

    print(f"\nWrote {len(records)} answer(s) -> {out}")
    print(f"Next: python scripts/run_e008.py code --answers {out}")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Coding — four outcomes, against a discriminator written before the answers
# ─────────────────────────────────────────────────────────────────────────────


def load_coding(path: Path, answers: Path, fixture: dict) -> list[dict]:
    """Coding rows, created from the answers on first use."""
    if path.exists():
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not answers.exists():
        raise SystemExit(f"No answers at {answers}. Run `generate` first.")
    by_id = {p["id"]: p for p in fixture["probes"]}
    rows = []
    for line in answers.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        probe = by_id[record["probe_id"]]
        rows.append(
            {
                "probe_id": record["probe_id"],
                "construct": record["construct"],
                "split": record["split"],
                "question": record["question"],
                "answer": record["text"],
                "graph_says": probe["graph_says"],
                "memory_says": probe["memory_says"],
                "evidence_present": record["evidence_present"],
                "outcome": "",
                "comment": "",
            }
        )
    return rows


def write_coding(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def code(args: argparse.Namespace) -> int:
    """Print one probe with its answer and its pre-written discriminator."""
    fixture = load_fixture(args.fixture)
    rows = load_coding(args.coding, args.answers, fixture)
    write_coding(args.coding, rows)

    pending = [r for r in rows if not r["outcome"]]
    chosen = [r for r in rows if r["probe_id"] == args.id] if args.id else pending[: args.count]
    if not chosen:
        print("Every probe is coded. Next: `run_e008.py report`.")
        return 0

    done = len(rows) - len(pending)
    for i, row in enumerate(chosen, start=1):
        print(RULE)
        print(f"{row['probe_id']}  {row['construct']}/{row['split']}  "
              f"[{i} of {len(chosen)} shown; {done}/{len(rows)} coded]")
        if not row["evidence_present"]:
            print("  RETRIEVAL MISS — the fiction did not reach the subgraph.")
            print("  Excluded from the leak denominator; code it anyway for the record.")
        print("\n  QUESTION")
        print(wrap(row["question"]))
        print("\n  GRAPH SAYS (written before any answer existed)")
        print(wrap(row["graph_says"]))
        print("\n  MEMORY SAYS")
        print(wrap(row["memory_says"]))
        print("\n  ANSWER")
        print(wrap(row["answer"]))
        print()
        print(CODING_CRIB)
        print(f"\n  coded: {row['outcome'] or '—'}")
        print(f"  -> python scripts/run_e008.py set {row['probe_id']} <{'|'.join(OUTCOMES)}>")
    print(RULE)
    return 0


def set_outcome(args: argparse.Namespace) -> int:
    """Record one probe's outcome."""
    fixture = load_fixture(args.fixture)
    rows = load_coding(args.coding, args.answers, fixture)
    matches = [r for r in rows if r["probe_id"] == args.probe_id]
    if not matches:
        raise SystemExit(f"No probe {args.probe_id} in {args.coding}.")
    matches[0]["outcome"] = args.outcome
    if args.comment:
        matches[0]["comment"] = args.comment
    write_coding(args.coding, rows)
    done = sum(1 for r in rows if r["outcome"])
    print(f"{args.probe_id}: {args.outcome}   [{done}/{len(rows)} coded]")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Report — the registered rule, applied
# ─────────────────────────────────────────────────────────────────────────────


def report(args: argparse.Namespace) -> int:
    """Apply E-008's decision rule. Nothing is decided here."""
    if not args.coding.exists():
        raise SystemExit(f"No coding at {args.coding}. Run `code` first.")
    rows = [json.loads(line) for line in args.coding.read_text(encoding="utf-8").splitlines() if line.strip()]
    held = [r for r in rows if r["split"] == "held_out"]
    pending = [r for r in held if not r["outcome"]]
    if pending:
        raise SystemExit(f"{len(pending)} held-out probe(s) uncoded. The rule runs on the whole set.")

    verified = [r for r in held if r["evidence_present"]]
    misses = len(held) - len(verified)
    tally = {outcome: sum(1 for r in verified if r["outcome"] == outcome) for outcome in OUTCOMES}
    leaks = [r["probe_id"] for r in verified if r["outcome"] == "leak"]
    followed = tally["followed_graph"] / len(verified) if verified else 0.0

    print(f"held-out probes {len(held)}   evidence verified {len(verified)}   retrieval misses {misses}")
    print(f"outcomes over the verified: {tally}")
    print(f"followed_graph {followed:.3f} against a floor of {FOLLOW_FLOOR}")
    print()
    if leaks:
        print(f"LEAK on {len(leaks)} probe(s): {', '.join(leaks)}")
    clean = not leaks and followed >= FOLLOW_FLOOR and bool(verified)
    if clean:
        bound = 3 / len(verified)
        print("Both registered conditions hold: zero leaks and the follow floor cleared.")
        print(f"The claim this licenses: the per-probe leak rate is at most {bound:.3f} (95%,")
        print(f"rule of three over {len(verified)} verified probes). NOT 'no parametric leakage'.")
    else:
        print("The grounded claim does NOT hold. Report it; do not re-iterate on held-out probes.")
        if not leaks and followed < FOLLOW_FLOOR:
            print("  Zero leaks with the floor missed is the all-refused shape the second")
            print("  condition exists to catch — refusing everything is not grounding.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
    common.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    common.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    common.add_argument("--kind-cap", type=int, default=DEFAULT_KIND_CAP)
    common.add_argument("--split", choices=("dev", "held_out", "all"), default="all")

    loader = sub.add_parser("load", parents=[common], help="create the fictional constructs")
    loader.add_argument("--force", action="store_true")
    loader.set_defaults(func=load)

    ver = sub.add_parser("verify", parents=[common], help="retrieve and check the fiction arrived")
    ver.add_argument("--out", type=Path, default=RETRIEVAL_PATH)
    ver.set_defaults(func=verify)

    clean = sub.add_parser("verify-clean", help="assert the graph holds no fixture nodes")
    clean.set_defaults(func=verify_clean)

    gen = sub.add_parser("generate", parents=[common], help="one answer per probe (paid)")
    gen.add_argument("--retrieval", type=Path, default=RETRIEVAL_PATH)
    gen.add_argument("--out", type=Path, default=None)
    gen.add_argument("--model", default=None)
    gen.add_argument("--limit", type=int, default=0)
    gen.add_argument("--dry-run", action="store_true")
    gen.add_argument("--force", action="store_true")
    gen.set_defaults(func=generate)

    coder = sub.add_parser("code", help="one probe, its answer, and the discriminator")
    coder.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
    coder.add_argument("--answers", type=Path, default=ANSWERS_PATH.with_name("e008_answers_held_out.jsonl"))
    coder.add_argument("--coding", type=Path, default=CODING_PATH)
    coder.add_argument("--id")
    coder.add_argument("--next", action="store_true")
    coder.add_argument("--count", type=int, default=1)
    coder.set_defaults(func=code)

    setter = sub.add_parser("set", help="record one probe's outcome")
    setter.add_argument("probe_id")
    setter.add_argument("outcome", choices=OUTCOMES)
    setter.add_argument("--comment", default="")
    setter.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
    setter.add_argument("--answers", type=Path, default=ANSWERS_PATH.with_name("e008_answers_held_out.jsonl"))
    setter.add_argument("--coding", type=Path, default=CODING_PATH)
    setter.set_defaults(func=set_outcome)

    rep = sub.add_parser("report", help="apply the registered decision rule")
    rep.add_argument("--coding", type=Path, default=CODING_PATH)
    rep.set_defaults(func=report)

    down = sub.add_parser("teardown", help="delete every fixture node and prove it")
    down.set_defaults(func=teardown)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
