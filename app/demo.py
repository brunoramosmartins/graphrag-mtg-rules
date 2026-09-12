"""Live demo: a question, a grounded answer, and the subgraph it came from.

Runs against a **live Neo4j** — the same retrieval stack the experiments ran,
not a replay of `runs/`. Cold start parses the Comprehensive Rules and reads
the Scryfall bulk once, then every question is a real traversal.

Three things this demo refuses to do, each of which would make it prettier:

**It does not claim the shipped configuration it is not running.** Arm C's
text half is TF-IDF here (pin 12's registered ablation), not the dense hybrid.
The dense half needs a 115k-document corpus built and an embedding call per
question — a cold start measured in minutes and a cost per click. The router
sends only a minority of questions to the text half at all, so the graph
behaviour on display is the real one; the sidebar says which half is wired and
why, because a demo that quietly runs an ablation and is read as the product
is the same defect as a harness that ran arm C and filed it as arm B.

**It does not draw an edge it does not have.** Text-retrieved evidence carries
no traversal — its `path` is a sentence, not a path — and it is listed apart
from the graph rather than attached to it with an invented arrow.

**It does not spend a token without being asked.** Retrieval is free and runs
on submit; generation is a separate button that prints the context size first,
per the project's cost rule.

Run:
    docker compose up -d --wait
    streamlit run app/demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from examples import resolve  # noqa: E402  (app-local)
from paths import FRIENDLY, build_graph, has_path, widest_level  # noqa: E402  (app-local)

from graphrag_mtg.etl.cr_parser import CR_TXT_PATH
from graphrag_mtg.extraction.llm import LlmClient
from graphrag_mtg.generation.answerer import answer as generate_answer
from graphrag_mtg.graph.connection import driver_session
from graphrag_mtg.retrieval.pipeline import neo4j_runner, retrieve
from graphrag_mtg.retrieval.subgraph import DEFAULT_KIND_CAP, DEFAULT_TOKEN_BUDGET, Outcome

MAX_ANSWER_TOKENS = 700

NOTICE = (
    "*Unofficial Fan Content permitted under the Fan Content Policy. Not "
    "approved/endorsed by Wizards. Portions of the materials used are property "
    "of Wizards of the Coast. ©Wizards of the Coast LLC.* "
    "Card data provided by [Scryfall](https://scryfall.com). "
    "Strictly non-commercial."
)

KIND_ICON = {"rule": "§", "ruling": "¶", "card": "▣", "keyword": "◈", "legality": "✦"}


@st.cache_resource(show_spinner="Parsing the Comprehensive Rules and the Scryfall bulk…")
def load_stack():
    """The retrieval stack plus the card facts the page displays.

    The stack comes from the experiment harness rather than being rebuilt
    here: a demo that assembles its own linker is a demo that can drift from
    what was measured, and then the screenshot and the table disagree.

    The bulk is read **once** and handed to `build_stack`, which otherwise
    reads it itself. A second full pass to collect image URLs would double a
    cold start for data already in memory.
    """
    from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, bulk_path, iter_bulk
    from run_e007 import build_stack

    cards = list(iter_bulk(bulk_path(ORACLE_CARDS_STEM)))
    # Keyed by **name**, because that is what card evidence carries: the
    # retrieval layer's `key` for a card is `Humility`, not its oracle id.
    # Keying this by oracle_id would look right, resolve nothing, and show
    # no image at all with no error anywhere.
    facts = {
        card["name"]: {
            "name": card["name"],
            "type_line": card.get("type_line", ""),
            "mana_cost": card.get("mana_cost", ""),
            # Displayed from Scryfall's own CDN, never copied into the repo:
            # the Fan Content posture permits showing them, not shipping them.
            "image": (card.get("image_uris") or {}).get("normal", ""),
            "scryfall": card.get("scryfall_uri", ""),
        }
        for card in cards
        if card.get("name")
    }
    return (*build_stack(CR_TXT_PATH, cards=cards), facts)


@st.cache_data(show_spinner=False)
def examples() -> tuple[list[dict], int]:
    """Development questions whose text this checkout actually has."""
    from split_golden import QUESTION_FILES, load_questions

    rows = load_questions(ROOT / "data" / "golden", QUESTION_FILES)
    dev = set(
        json.loads(
            (ROOT / "data" / "golden" / "phase4_dev_ids.json").read_text(encoding="utf-8")
        )["dev_ids"]
    )
    # Development questions only. The 57 evaluation questions were opened
    # once, and a demo that invites clicking through them is a second look at
    # the split by another name.
    return resolve([row for row in rows if row["id"] in dev], ROOT)


COLOURS = {"Rule": "#4c78a8", "Card": "#f58518", "Ruling": "#54a24b",
           "Keyword": "#b279a2", "Format": "#e45756"}
FRIENDLY_PLURAL = {"Rule": "Rules", "Card": "Cards", "Ruling": "Official rulings",
                   "Keyword": "Keywords", "Format": "Formats"}


def render_graph(subgraph) -> None:
    try:
        from streamlit_agraph import Config, Edge, Node, agraph
    except ImportError:
        st.info(
            "Install the app extra for the graph view: `pip install -e .[app]`. "
            "The evidence and its paths are listed below either way."
        )
        return

    nodes, edges = build_graph(subgraph.evidence)
    if not nodes:
        st.info("No traversal produced this evidence — see the text-retrieved items below.")
        return

    drawn = [
        Node(
            id=node.id,
            label=node.label,
            title=node.title,  # hover: identifies the node, does not hold it
            size=26 if node.seed else 16,
            color=COLOURS.get(node.kind, "#9d9d9d"),
            # A seed is what the question itself named. Ringing it is what
            # makes the picture a *traversal* rather than a bag of nodes:
            # the viewer can see where the walk started and how far it got.
            borderWidth=4 if node.seed else 1,
            borderWidthSelected=5,
            font={"size": 16, "face": "sans-serif"},
        )
        for node in nodes
    ]

    # These subgraphs are traversal trees rooted at the seeds, so a
    # left-to-right hierarchy is the shape they actually have. The force
    # layout drew them as a clump in one corner of a wide canvas — half the
    # screen empty and the reading order invented by the physics engine.
    config = Config(
        # Sized by the widest rank, not the node count: eight nodes three deep
        # need four rows. Sizing by the total gave a canvas twice as tall as
        # the drawing and a screenful of white space under it.
        height=max(320, min(720, 120 + 86 * widest_level(nodes, edges))),
        width=820,
        directed=True,
        physics=False,
        hierarchical=True,
        direction="LR",
        sortMethod="directed",
        levelSeparation=210,
        nodeSpacing=110,
        treeSpacing=120,
    )
    # `Config` stores width as "<n>px"; vis.js accepts a percentage and then
    # the canvas follows the browser instead of a number picked here.
    config.width = "100%"
    clicked = agraph(
        nodes=drawn,
        edges=[Edge(source=a, target=b, label=rel) for a, b, rel in edges],
        config=config,
    )

    # The hover card is clipped by the widget, so the full text lives here.
    selected = next((node for node in nodes if node.id == clicked), None)
    if selected is not None and selected.text:
        st.markdown(f"**{selected.label}** — {FRIENDLY.get(selected.kind, selected.kind)}")
        st.write(selected.text)

    present = sorted({node.kind for node in nodes})
    swatches = " ".join(
        f"<span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
        f"background:{COLOURS.get(kind, '#9d9d9d')};margin-right:4px'></span>"
        f"{FRIENDLY_PLURAL.get(kind, kind)}&nbsp;&nbsp;"
        for kind in present
    )
    st.markdown(
        f"<div style='font-size:0.85em;opacity:0.8'>{swatches}"
        "<b>thick ring</b> = named by the question &nbsp; · &nbsp; "
        "arrows run left to right, from what the question named to what the "
        "traversal reached &nbsp; · &nbsp; <b>click a node</b> to read it</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="GraphRAG over the MTG rules", layout="wide")
    st.title("GraphRAG over the Magic: The Gathering rules")

    with st.sidebar:
        st.subheader("What is wired")
        st.markdown(
            "- **Graph:** live Neo4j traversal\n"
            "- **Text half:** TF-IDF (pin 12's registered ablation)\n"
            "- **Not wired:** the dense hybrid half — it needs a 115k-document "
            "corpus and an embedding call per question"
        )
        st.subheader("What the evaluation says")
        st.markdown(
            "On the 57-question evaluation split, judge-scored correctness was "
            "**0.60 / 0.61 / 0.65** for vector / graph / hybrid, and **every "
            "registered per-stratum test came back inconclusive**. The vector "
            "baseline is ahead on the multi-hop stratum this project's "
            "hypothesis was written about. Details in `docs/evaluation.md`."
        )
        budget = st.slider("Token budget", 1000, 12000, DEFAULT_TOKEN_BUDGET, step=500)
        kind_cap = st.slider("Per-kind cap", 2, 40, DEFAULT_KIND_CAP)

    pool, withheld = examples()
    labels = ["(type my own)"] + [
        f"[{row['stratum']}] {row['question'][:90]}" for row in pool
    ]
    choice = st.selectbox("Example from the development split", labels)
    default = "" if choice == labels[0] else pool[labels.index(choice) - 1]["question"]
    question = st.text_area("Question", value=default, height=90)
    if withheld:
        st.caption(
            f"{withheld} of the {len(pool) + withheld} development questions are not "
            "listed: they are RulesGuru questions, whose text is **not redistributed "
            "in this repository**. The golden set versions their ids and a gitignored "
            "fetch script retrieves the text. Type any question above instead."
        )

    # Retrieval runs on the click and nowhere else. Streamlit reruns the whole
    # script on every widget interaction, so a retrieval guarded only by "is
    # there a question" re-traverses on each rerun — and this one also cleared
    # the answer, which meant pressing *Generate* produced an answer and then
    # threw it away on the rerun that followed.
    if st.button("Retrieve", type="primary") and question.strip():
        linker, rule_search, oracle_text, _facts = load_stack()
        with st.spinner("Traversing…"), driver_session() as session:
            st.session_state.subgraph = retrieve(
                question,
                linker=linker,
                run=neo4j_runner(session),
                rule_search=rule_search,
                oracle_text=oracle_text,
                token_budget=budget,
                kind_cap=kind_cap,
            )
            st.session_state.question = question
            st.session_state.pop("answer", None)

    subgraph = st.session_state.get("subgraph")
    if subgraph is None:
        st.caption(NOTICE)
        return

    left, right = st.columns([2, 3])
    with left:
        st.metric("Evidence items", len(subgraph.evidence))
        st.metric("Context tokens", subgraph.tokens)
        st.write(f"**Outcome:** `{subgraph.outcome.name}`")
        st.write("**Templates run:** " + (", ".join(subgraph.templates_run) or "none"))
        if subgraph.dropped or subgraph.capped:
            st.warning(
                f"Trimmed to fit the budget — dropped {dict(subgraph.dropped)}, "
                f"capped {dict(subgraph.capped)}"
            )
    with right:
        if subgraph.outcome is not Outcome.RESOLVED:
            st.error(
                f"Retrieval returned `{subgraph.outcome.name}`. The answer below, "
                "if any, is the pipeline declining rather than the model failing — "
                "the distinction E-007 exists to keep."
            )

    st.subheader("The subgraph")
    render_graph(subgraph)

    traversed = sum(1 for e in subgraph.evidence if has_path(e))
    st.subheader(
        f"Evidence — {traversed} traversed, {len(subgraph.evidence) - traversed} "
        "text-retrieved"
    )
    _, _, _, facts = load_stack()
    # Matched through the subgraph's own handle table, not through `cite()`.
    # A ruling is handed to the model as `ruling:1` — an ordinal, because a
    # model asked to copy 32 hex characters gets them wrong — while `cite()`
    # returns the real id. Comparing the two marks every ruling uncited.
    answered = st.session_state.get("answer")
    written = set(getattr(answered, "handles", []) or [])
    cited = {item for handle, item in subgraph.handles().items() if handle in written}

    for item in subgraph.evidence:
        icon = KIND_ICON.get(item.kind, "•")
        card = facts.get(item.key) if item.kind == "card" else None
        title = card["name"] if card else f"{item.kind} {item.key}"
        mark = " ✓ cited" if item in cited else ""
        with st.expander(f"{icon} **{title}** — {item.text[:80]}…{mark}"):
            if card and card["image"]:
                picture, prose = st.columns([1, 2])
                with picture:
                    # From Scryfall's CDN by URL. The repository never holds a
                    # card image; the Fan Content posture permits displaying
                    # them, not redistributing them.
                    st.image(card["image"], width=220)
                    if card["scryfall"]:
                        st.caption(f"[View on Scryfall]({card['scryfall']})")
                with prose:
                    st.caption(f"{card['mana_cost']}  ·  {card['type_line']}")
                    st.write(item.text)
            else:
                st.write(item.text)
            st.caption(
                f"via **{item.template}**, {item.distance} hop(s) from a named entity  \n"
                f"`{item.path or '(no path recorded)'}`  \n"
                f"cite as `{item.cite()}`"
            )

    st.subheader("Answer")
    st.caption(
        f"Generating sends **{subgraph.tokens}** context tokens plus the prompt to the "
        "model. Nothing has been spent yet."
    )
    # Disabled with its reason rather than clickable and inert: a button that
    # accepts the click and does nothing reads as a broken model call.
    if st.button(
        "Generate the answer",
        disabled=subgraph.is_empty,
        help="Retrieval returned no evidence; there is nothing to answer from."
        if subgraph.is_empty
        else None,
    ):
        client = LlmClient(max_tokens=MAX_ANSWER_TOKENS, temperature=0.0)
        with st.spinner("Generating…"):
            st.session_state.answer = generate_answer(
                st.session_state.question,
                subgraph,
                lambda system, prompt: client.complete_text(prompt, system=system),
                notice=True,
                model=client.model,
            )

    result = st.session_state.get("answer")
    if result is not None:
        if result.refused:
            st.warning(
                "Refused. " + ("The model declined." if result.generated else
                               "Retrieval produced nothing and no tokens were spent.")
            )
        # `rendered` is the **audit** format — every path spelled out inline,
        # `[path: (:Card {Humility})] [card Humility]`. That is right for a
        # verdict file and unreadable as prose, so the page shows the bare
        # markers and keeps the audit trail one click away, losing nothing.
        st.markdown(result.text or "_(nothing)_")
        with st.expander("Citation trail (the audit format, paths spelled out)"):
            st.markdown(result.rendered or "_(nothing)_")

        if result.unknown:
            # A cited handle the subgraph does not contain is a fabricated
            # citation, detected mechanically. Shown, never swallowed.
            st.error(f"Fabricated citation(s): {', '.join(result.unknown)}")

        used = len({item for handle, item in subgraph.handles().items()
                    if handle in set(result.handles)})
        total = len(subgraph.evidence)
        st.caption(f"Cited **{used} of {total}** retrieved item(s): "
                   f"{', '.join(result.handles) or 'none'}")
        if total and used <= total / 3:
            # Not a complaint about this answer — a measurement the project
            # already made twice. E-009 found the failure is grounding rather
            # than retrieval, and an answer resting on a fraction of its
            # evidence is what that looks like from the reader's side.
            st.info(
                "Most of the retrieved evidence went uncited. The evaluation "
                "found the same thing: the weak link in this pipeline is "
                "**grounding**, not retrieval — the model reaches the answer "
                "without leaning on most of what it was given."
            )

    st.divider()
    st.caption(NOTICE)


if __name__ == "__main__":
    main()
