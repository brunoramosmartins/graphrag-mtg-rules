# A check that cannot run reports identically to the thing it checks having failed

**Cross-phase · drafted 2026-09-12**

> **SKELETON.** The instances are all real and verified; the prose is not
> written. This one is not tied to a phase — it is the failure shape that
> recurred most across the project, and it is the most portable thing here.

<!-- write: opening. A broken probe and a broken subject produce the same
     output. The operator sees "failed" and debugs the wrong half. -->

---

## The shape

<!-- write: state it once, abstractly. A check has two ways to return
     negative: the thing is broken, or the check could not execute. Most
     checks do not distinguish them, and the second is invisible. -->

---

## Five instances from this project

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
     - when a check passes on the first try, be suspicious of the check. -->

---

## Lessons Learned

<!-- FIRST PERSON, written by the author. Not to be ghost-written. -->

## Failed Attempts

<!-- FIRST PERSON, written by the author. Not to be ghost-written. -->
