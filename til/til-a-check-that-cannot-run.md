# A check that cannot run reports identically to the thing it checks having failed

**Cross-phase · drafted 2026-09-12**

> **SKELETON.** The instances are all real and verified; the prose is not
> written. This one is not tied to a phase — it is the failure shape that
> recurred most across the project, and it is the most portable thing here.
> The sixth, added 2026-09-13, runs the shape backwards and cost the most.

<!-- write: opening. A broken probe and a broken subject produce the same
     output. The operator sees "failed" and debugs the wrong half. -->

---

## The shape

<!-- write: state it once, abstractly. A check has two ways to return
     negative: the thing is broken, or the check could not execute. Most
     checks do not distinguish them, and the second is invisible.

     Then state the inversion, because instance 6 is the expensive one: a
     check can also have two ways to return POSITIVE, one of which is the
     failure it was built to catch. That version is harder to see, because
     nobody inspects a pass. -->

---

## Six instances from this project

### 1. A healthcheck against an image with no shell

Phoenix ran a `CMD-SHELL` healthcheck. The image is distroless — **no
`/bin/sh`** — so the probe returned `exec failed`, and `compose up --wait`
reported the container as unhealthy. The service was fine the whole time.

<!-- write: the tell. Rewritten as exec form calling Python directly. -->

### 2. `--help` crashing on a Windows console

A CLI docstring held `∩`. On a cp1252 console `--help` raised
`UnicodeDecodeError` — the tool reporting itself as broken when only its
*help text* was unprintable.

Worse, the ad-hoc scan written to find the offenders reported **zero**,
because it only inspected files whose source began with `"""`. The scan was
itself a check that could not run. A test found two more.

### 3. A control that blamed the thing it was controlling

The key-fidelity harness scored the judge against deliberately wrong keys. Its
first run read 25/30 — and the script printed a cause it had no way to
observe. Four of the five "failures" were fixture defects: the perturbed key
endorsed a verdict while its reasoning still contradicted it.

<!-- write: the fix was two things — repair the fixtures, and stop the scorer
     naming a cause it cannot see. -->

### 4. Auto-fit that lived inside the pass we had turned off

The demo's graph drew in the middle third of a wide canvas. `vis.js` runs
`stabilization.fit` — the call that zooms the view to the drawing — **inside
the physics pass**. Physics had been disabled deliberately, for layout
stability. Disabling it disabled auto-fit silently.

### 5. A verifier that agreed with itself

<!-- write: E-001 pin 10 registered a re-verification of the legality answer
     keys against the bulk the run would read, and nothing implemented it for
     a month. The shape to name: a verifier that recomputes the frozen hash
     from the golden row rather than from the bulk matches every time,
     including the times that matter. `tests/test_legality_keys.py` pins
     exactly that property. -->

### 6. The inversion: two ways to return *positive*

<!-- write: this one runs the shape backwards and is the strongest instance,
     so it may deserve to lead rather than close. -->

The five above are checks with two ways to return negative. This one has two
ways to return **positive**, and one of them is the failure being checked for.

`answer_path` was the guard that decided whether a question was usable: it
walked the retrieved evidence for a chain from the seed to the answer, and
returning `None` excluded the question. Callers tested `chain is None`. There
was nothing else to test.

But a chain to *an accepted answer string* and a chain that *answers the
question* both come back non-empty, and they are indistinguishable at the call
site. A three-hop question asking `directed_by` was satisfied by a one-step
`written_by` edge, because the person on the far end of it was also in the
answer set. **126 of 137 questions in that cell passed the guard this way.**

The model, handed hop one and eleven unrelated facts, refused — which its
grounding prompt instructs — and the refusal was scored as a generation
failure. The guard had reported a pass, so nobody looked at what it passed.

<!-- write: the tell, and it is the general one. Ask what ELSE would make this
     check return the answer it just returned. A probe that cannot fail is the
     famous version; a probe that passes for two different reasons is the same
     defect and is harder to see, because the passing case is the one nobody
     inspects. The repair: make the check state the property, not the
     outcome - answer_path now takes a required `hops` and returns a chain of
     exactly that depth, so "passed" has one meaning. -->

<!-- write: the cost. Five months of measurement, three published documents and
     one funded follow-up experiment rested on it. It was found by printing a
     single case, which took an afternoon and had been possible from day one. -->

---

## Detection

<!-- write: 4-5 portable rules. Candidates:
     - a probe must be able to fail; prove it by running it against a known
       broken input, not a known good one;
     - assert positive evidence — output exists AND has the expected shape AND
       shows the behaviour the fix enables;
     - separate "failed" from "could not run" in the exit code or the message;
     - a check whose cause is inferred rather than observed should say so
       instead of naming a cause;
     - when a check passes on the first try, be suspicious of the check;
     - ask what ELSE would make this check return what it just returned —
       a guard that passes for two reasons is the same defect as one that
       cannot fail, and it is harder to see because nobody inspects a pass;
     - make a guard state the property, not the outcome: a required `hops`
       argument gives "passed" exactly one meaning. -->

---

## Lessons Learned

<!-- FIRST PERSON, written by the author. Not to be ghost-written. -->

## Failed Attempts

<!-- FIRST PERSON, written by the author. Not to be ghost-written. -->
