"""The correctness rubric, shared verbatim by the human and the judge.

E-011 registers the judge's threshold as the lower bound of a human
self-agreement ceiling, "scored as exact agreement on the same correctness
rubric the judge uses". That sentence only means something if there is one
rubric — a single constant both readers are handed — rather than a prompt
for the model and a habit for the human. So the text lives here, the judge
prompt is built from it, the worksheet prints it, and
:func:`rubric_hash` is what the freeze records.

Two design choices are registered rather than inferred, because both are
places where a label can quietly follow the result:

**Refusals are not a correctness label.** A refusal is recorded as an
outcome and excluded from the ceiling's denominator. Including it would
hand both passes a free agreement on every refused row — the human is not
judging anything there, they are reading a flag — and the ceiling, which
becomes the judge's pass mark, would be inflated by exactly the rows that
required no judgement. Downstream, in the head-to-head, a refusal on an
answerable question still counts as a miss; that is a scoring rule, not a
label, and it belongs to E-001.

**The middle label's boundaries are fixed before any label exists.**
E-007c found `partial` applied to 25 of 42 subgraphs and then found the
disagreement sitting on the boundary its own prediction called easy. A
middle category absorbs uncertainty unless its edges are pinned in
advance, so the tie-breaks below are part of the rubric text and are
hashed with it.
"""

from __future__ import annotations

import hashlib
import re
from enum import Enum

from graphrag_mtg.generation.citations import MARKER

#: Whitespace a removed handle leaves in front of its own sentence's
#: punctuation. Left in place it reads as a typo the model did not make,
#: and a reader who notices it knows a handle stood there — which is the
#: arm-identifying cue the blinding exists to remove.
_ORPHANED_SPACE = re.compile(r"\s+([,.;:!?)\]])")

#: Bumped whenever RUBRIC changes. The version travels with every label
#: and every judged verdict, so a figure can always name the text it was
#: produced under.
RUBRIC_VERSION = "p6-c1"


class Correctness(str, Enum):
    """The three-way correctness label. Refusal is an outcome, not a label."""

    CORRECT = "correct"
    PARTIAL = "partial"
    INCORRECT = "incorrect"
    #: The answer key does not answer the question asked. Excluded from
    #: every denominator, reported as a count.
    VOID = "void"


#: Labels that carry a judgement and therefore belong in the ceiling.
JUDGED = (Correctness.CORRECT, Correctness.PARTIAL, Correctness.INCORRECT)

RUBRIC = """\
Score the ANSWER against the KEY. The key is the only authority.

You are not being asked whether the answer is right about Magic. You are
being asked whether it says what the key says. If you know the key is
wrong, the key still wins and the row is scored against it — a reader who
corrects from their own knowledge is measuring their knowledge, not the
system's.

LABELS

  correct     The answer reaches the key's verdict, and every assertion it
              makes is either stated by the key or left untouched by it.

  partial     The answer reaches the key's verdict but is materially
              incomplete or arrives there by reasoning the key contradicts.

  incorrect   The answer's verdict contradicts the key, or the answer
              asserts something the key contradicts.

  void        The key does not answer the question asked. Not a judgement
              about the answer; excluded from every denominator.

TIE-BREAKS, fixed before any label exists

  1. Correct reasoning beyond what the key states never lowers the label.
     A longer answer is not a worse one.

  2. An assertion the key neither states nor contradicts is `partial`,
     never `incorrect`. Calling it incorrect requires knowing it is false,
     which is knowledge the key did not supply.

  3. The right verdict by reasoning the key contradicts is `partial`, not
     `correct`. A judge-level answer is the explanation, not the yes.

  4. A hedged answer that reaches the key's verdict and names what it is
     missing is `correct`. The context block itself invites that notice,
     and penalising it would score the design rather than the answer.

  5. Missing an element the key treats as part of its verdict is
     `partial`. Missing an element the key mentions in passing is not.

  6. Formatting, citation handles, ordering and verbosity are never
     grounds for a label.
"""

#: What the reader is shown, and the reason it is shown that way.
BLINDING = """\
Citation handles are stripped before judgement. Correctness asks whether
the answer matches the key; whether its citations hold up is a different
measurement with its own instrument. Stripping them also means the graph
arm and the vector arm reach the reader looking alike, which is what
E-011 requires of the head-to-head audit — so the ceiling is measured on
exactly the rendering the head-to-head will use, not a friendlier one.
"""


def rubric_hash() -> str:
    """SHA-256 of the rubric text, version and blinding rule together.

    This is what a freeze records. If any of the three moves, a worksheet
    built under the old text can no longer be compared with one built
    under the new, and the tools refuse rather than quietly averaging two
    instruments.
    """
    payload = f"{RUBRIC_VERSION}\n{RUBRIC}\n{BLINDING}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render_for_judgement(text: str) -> str:
    """Strip citation handles, leaving the prose both arms are judged on.

    Args:
        text: A generated answer, as written by the model.

    Returns:
        The same answer with ``[kind:key]`` handles removed and the
        whitespace they leave behind collapsed.
    """
    stripped = MARKER.sub("", text)
    lines = [_ORPHANED_SPACE.sub(r"\1", " ".join(line.split())) for line in stripped.splitlines()]
    return "\n".join(lines).strip()
