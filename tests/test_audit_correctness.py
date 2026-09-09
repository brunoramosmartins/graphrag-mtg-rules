"""The correctness ceiling harness: what it refuses, and why each refusal.

Every test here corresponds to a way the ceiling could come out too high.
The number this tool produces becomes the judge's pass mark under E-011,
so a guard that silently does nothing is worse than no guard — it reads
as evidence that a check was performed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import audit_correctness as ac


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
    )
    return path


def answer(
    qid: str, *, refused: bool = False, text: str = "Yes [rule:1.1].", notice: bool = True
) -> dict:
    return {
        "question_id": qid,
        "text": text,
        "refused": refused,
        "notice": notice,
        "model": "gpt-4o-mini",
        "prompt_version": "p5-a3",
    }


@pytest.fixture
def golden(tmp_path: Path) -> tuple[Path, Path]:
    """A three-shard golden set and its development split.

    `build`'s contamination guard derives E-001's evaluation set from
    these, so the fixture has to be shaped like the real one rather than
    stubbed out — the guard is the thing under test.
    """
    directory = tmp_path / "golden"
    rows = [{"id": f"g-{i}", "stratum": "definition_1hop"} for i in range(4)]
    write_jsonl(directory / "ids_v0.jsonl", rows[:2])
    write_jsonl(directory / "authored_v0.jsonl", rows[2:3])
    write_jsonl(directory / "definitions_v0.jsonl", rows[3:])
    split = directory / "phase4_dev_ids.json"
    split.write_text(json.dumps({"dev_ids": ["g-0"]}), encoding="utf-8")
    return directory, split


def build_args(tmp_path: Path, golden: tuple[Path, Path], answers: list[Path], **kw):
    directory, split = golden
    defaults = {
        "answers": answers,
        "golden": directory,
        "split": split,
        "out": tmp_path / "m1.json",
        "n": 0,
        "seed": 1,
        "batch": "b1",
        "cache_dir": [tmp_path / "cache"],
        "force": False,
    }
    return argparse.Namespace(**{**defaults, **kw})


class TestGatherAnswers:
    def test_refuses_two_generators_in_one_pool(self, tmp_path: Path) -> None:
        # A ceiling pooled across two generators describes neither, and the
        # mixture is not what Phase 6 will judge.
        first = write_jsonl(tmp_path / "a.jsonl", [answer("q1")])
        other = answer("q2")
        other["prompt_version"] = "p5-a2"
        second = write_jsonl(tmp_path / "b.jsonl", [other])
        with pytest.raises(SystemExit, match="mix generators"):
            ac.gather_answers([first, second])

    def test_refuses_a_notice_mismatch(self, tmp_path: Path) -> None:
        # An arm invited to hedge writes prose of a different shape, and
        # how hard a hedge is to re-judge is what this instrument measures.
        first = write_jsonl(tmp_path / "a.jsonl", [answer("q1", notice=True)])
        second = write_jsonl(tmp_path / "b.jsonl", [answer("q2", notice=False)])
        with pytest.raises(SystemExit, match="mix generators"):
            ac.gather_answers([first, second])

    def test_a_missing_notice_field_reads_as_on(self, tmp_path: Path) -> None:
        # E-007's answers predate the field and were generated with the
        # notice live; defaulting the other way would mislabel a whole batch.
        row = answer("q1")
        del row["notice"]
        path = write_jsonl(tmp_path / "a.jsonl", [row])
        assert ac.gather_answers([path])[1]["notice"] is True

    def test_refuses_the_same_question_twice(self, tmp_path: Path) -> None:
        first = write_jsonl(tmp_path / "a.jsonl", [answer("q1")])
        second = write_jsonl(tmp_path / "b.jsonl", [answer("q1", text="No [rule:2.2].")])
        with pytest.raises(SystemExit, match="two answer files"):
            ac.gather_answers([first, second])

    def test_reports_the_shared_provenance(self, tmp_path: Path) -> None:
        path = write_jsonl(tmp_path / "a.jsonl", [answer("q1"), answer("q2")])
        answers, provenance = ac.gather_answers([path])
        assert set(answers) == {"q1", "q2"}
        assert provenance == {
            "model": "gpt-4o-mini",
            "prompt_version": "p5-a3",
            "notice": True,
        }


class TestBuild:
    def test_excludes_refusals_from_the_worksheet(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # Both passes agree on a refusal without reading anything. Those
        # free agreements would inflate the exact number that becomes the
        # judge's pass mark.
        path = write_jsonl(
            tmp_path / "a.jsonl",
            [answer("q1"), answer("q2", refused=True), answer("q3")],
        )
        args = build_args(tmp_path, golden, [path])
        assert ac.build(args) == 0
        meta = json.loads(args.out.read_text(encoding="utf-8"))
        assert set(meta["labels"]) == {"q1", "q3"}
        assert meta["refused_ids"] == ["q2"]
        assert meta["pool"] == {"total": 3, "refused": 1, "eligible": 2}

    def test_refuses_a_question_from_the_evaluation_split(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # g-1 is golden and not in the development draw, so it is E-001's
        # to score. A ceiling measured on it would make the instrument a
        # function of the data it grades.
        path = write_jsonl(tmp_path / "a.jsonl", [answer("q1"), answer("g-1")])
        with pytest.raises(SystemExit, match="evaluation split"):
            ac.build(build_args(tmp_path, golden, [path]))

    def test_allows_a_question_from_the_development_draw(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # g-0 is in the Phase 4 dev draw, which E-001 never scores.
        path = write_jsonl(tmp_path / "a.jsonl", [answer("q1"), answer("g-0")])
        args = build_args(tmp_path, golden, [path])
        assert ac.build(args) == 0
        assert set(json.loads(args.out.read_text(encoding="utf-8"))["labels"]) == {"q1", "g-0"}

    def test_refuses_to_overwrite_a_pass_in_progress(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # Rebuilding after labelling has started lets the sample follow the
        # labels, which is the failure the seed exists to prevent.
        path = write_jsonl(tmp_path / "a.jsonl", [answer("q1")])
        args = build_args(tmp_path, golden, [path])
        ac.build(args)
        with pytest.raises(SystemExit, match="already exists"):
            ac.build(build_args(tmp_path, golden, [path]))

    def test_records_the_rubric_it_was_built_under(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        path = write_jsonl(tmp_path / "a.jsonl", [answer("q1")])
        args = build_args(tmp_path, golden, [path])
        ac.build(args)
        meta = json.loads(args.out.read_text(encoding="utf-8"))
        assert meta["rubric_hash"] == ac.rubric_hash()
        assert meta["rubric_version"] == ac.RUBRIC_VERSION


class TestRequireSameProse:
    def test_fires_when_the_answers_are_regenerated(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        path = write_jsonl(tmp_path / "a.jsonl", [answer("q1")])
        args = build_args(tmp_path, golden, [path])
        ac.build(args)
        first = json.loads(args.out.read_text(encoding="utf-8"))
        write_jsonl(path, [answer("q1", text="No, actually [rule:2.2].")])
        with pytest.raises(SystemExit, match="prose has moved"):
            ac.require_same_prose(first)

    def test_ignores_a_change_the_blinding_removes(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # A label describes the prose the annotator read. A citation handle
        # moving is invisible to them, so it must be invisible to the guard.
        path = write_jsonl(tmp_path / "a.jsonl", [answer("q1", text="Yes [rule:1.1].")])
        args = build_args(tmp_path, golden, [path])
        ac.build(args)
        first = json.loads(args.out.read_text(encoding="utf-8"))
        write_jsonl(path, [answer("q1", text="Yes [rule:9.9][card:Rancor].")])
        ac.require_same_prose(first)


def prepared(tmp_path: Path, golden: tuple[Path, Path], labels: dict[str, str]) -> Path:
    """A frozen pass 1 carrying `labels`, on answers that stay on disk."""
    path = write_jsonl(tmp_path / "a.jsonl", [answer(qid) for qid in labels])
    args = build_args(tmp_path, golden, [path])
    ac.build(args)
    meta = json.loads(args.out.read_text(encoding="utf-8"))
    for qid, label in labels.items():
        meta["labels"][qid]["label"] = label
    meta["frozen"] = True
    meta["frozen_at"] = date.today().isoformat()
    args.out.write_text(json.dumps(meta), encoding="utf-8")
    return args.out


class TestReauditBuild:
    def test_refuses_before_the_registered_gap(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # A pass taken too soon measures recall, not judgement, and it
        # inflates the ceiling that becomes the judge's pass mark.
        source = prepared(tmp_path, golden, {"q1": "correct"})
        args = argparse.Namespace(
            source=source, out=tmp_path / "m2.json", min_days=5, seed=2, force=False
        )
        with pytest.raises(SystemExit, match="0 day"):
            ac.reaudit_build(args)

    def test_refuses_an_unfrozen_first_pass(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        path = write_jsonl(tmp_path / "a.jsonl", [answer("q1")])
        args = build_args(tmp_path, golden, [path])
        ac.build(args)
        with pytest.raises(SystemExit, match="not frozen"):
            ac.reaudit_build(
                argparse.Namespace(
                    source=args.out, out=tmp_path / "m2.json", min_days=0, seed=2, force=False
                )
            )

    def test_does_not_copy_the_first_pass_labels(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # A worksheet that carries the answer is not a blind pass.
        source = prepared(tmp_path, golden, {"q1": "correct", "q2": "incorrect"})
        out = tmp_path / "m2.json"
        ac.reaudit_build(
            argparse.Namespace(source=source, out=out, min_days=0, seed=2, force=False)
        )
        meta = json.loads(out.read_text(encoding="utf-8"))
        assert {row["label"] for row in meta["labels"].values()} == {""}
        assert meta["source_frozen_at"] == date.today().isoformat()


class TestCarriedFromPassOne:
    """A second pass inherits what describes the material, by name.

    `reaudit_build` listed the carried fields one at a time, and when
    `caches` and `golden` were added to `build` it silently did not carry
    them. `show` on a second pass over golden-set questions then looked
    only in E-007's cache and could not find the answer key. It failed
    loudly, which is the design — the defect is two constructors of one
    object drifting apart.
    """

    def test_the_carried_list_covers_what_build_writes(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        path = write_jsonl(tmp_path / "a.jsonl", [answer("q1")])
        args = build_args(tmp_path, golden, [path])
        ac.build(args)
        first = json.loads(args.out.read_text(encoding="utf-8"))
        # Everything in pass 1 is either carried, or is about the pass
        # itself rather than about the material under judgement.
        about_the_pass = {
            "pass", "frozen", "seed", "drawn_at", "frozen_at", "order", "labels",
            "exposed", "source", "source_frozen_at", "elapsed_days",
        }
        uncovered = set(first) - set(ac.CARRIED_FROM_PASS_1) - about_the_pass
        assert not uncovered, f"pass 1 writes {uncovered}, which pass 2 would not inherit"

    def test_the_cache_locations_reach_the_second_pass(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # The concrete failure: without `caches`, a second pass over
        # golden-set questions cannot resolve a key and stops.
        source = prepared(tmp_path, golden, {"q1": "correct"})
        out = open_second(tmp_path, source)
        first = json.loads(source.read_text(encoding="utf-8"))
        second = json.loads(out.read_text(encoding="utf-8"))
        assert second["caches"] == first["caches"]
        assert second["golden"] == first["golden"]

    def test_nothing_about_the_judgement_is_carried(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # A worksheet carrying pass 1's labels is not a blind pass, so the
        # carried list must describe the material and never the verdicts.
        assert "labels" not in ac.CARRIED_FROM_PASS_1
        assert "exposed" not in ac.CARRIED_FROM_PASS_1


class TestReauditScore:
    def second_pass(self, tmp_path: Path, source: Path, labels: dict[str, str]) -> Path:
        out = tmp_path / "m2.json"
        ac.reaudit_build(
            argparse.Namespace(source=source, out=out, min_days=0, seed=2, force=False)
        )
        meta = json.loads(out.read_text(encoding="utf-8"))
        for qid, label in labels.items():
            meta["labels"][qid]["label"] = label
        out.write_text(json.dumps(meta), encoding="utf-8")
        return out

    def test_refuses_while_a_row_is_unlabelled(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # Scoring now would let the rest be labelled against a visible
        # agreement rate.
        source = prepared(tmp_path, golden, {"q1": "correct", "q2": "partial"})
        out = self.second_pass(tmp_path, source, {"q1": "correct"})
        with pytest.raises(SystemExit, match="still unlabelled"):
            ac.reaudit_score(argparse.Namespace(out=out, also=[]))

    def test_excludes_void_pairs_from_the_denominator(
        self, tmp_path: Path, golden: tuple[Path, Path], capsys
    ) -> None:
        source = prepared(
            tmp_path, golden, {"q1": "correct", "q2": "partial", "q3": "void"}
        )
        out = self.second_pass(
            tmp_path, source, {"q1": "correct", "q2": "partial", "q3": "void"}
        )
        ac.reaudit_score(argparse.Namespace(out=out, also=[]))
        printed = capsys.readouterr().out
        assert "exact agreement 2/2" in printed
        assert "1 row(s) excluded" in printed

    def test_reports_a_disagreement(
        self, tmp_path: Path, golden: tuple[Path, Path], capsys
    ) -> None:
        source = prepared(tmp_path, golden, {"q1": "correct", "q2": "correct"})
        out = self.second_pass(tmp_path, source, {"q1": "correct", "q2": "partial"})
        ac.reaudit_score(argparse.Namespace(out=out, also=[]))
        printed = capsys.readouterr().out
        assert "exact agreement 1/2" in printed
        assert "q2: correct -> partial" in printed

    def test_a_thin_sample_gates_nothing(
        self, tmp_path: Path, golden: tuple[Path, Path], capsys
    ) -> None:
        # Two rows can reach 1.000 agreement. E-011's floor of 30 is what
        # stops that from becoming a judge threshold.
        source = prepared(tmp_path, golden, {"q1": "correct", "q2": "correct"})
        out = self.second_pass(tmp_path, source, {"q1": "correct", "q2": "correct"})
        ac.reaudit_score(argparse.Namespace(out=out, also=[]))
        assert "NOT gated" in capsys.readouterr().out


class TestExposedRows:
    def test_flagging_is_allowed_on_a_frozen_pass(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # Flagging changes no label — it changes what the score may claim.
        source = prepared(tmp_path, golden, {"q1": "correct", "q2": "partial"})
        ac.flag_exposed(
            argparse.Namespace(question_id="q1", reason="discussed elsewhere", out=source)
        )
        meta = json.loads(source.read_text(encoding="utf-8"))
        assert set(meta["exposed"]) == {"q1"}
        assert meta["labels"]["q1"]["label"] == "correct"

    def test_score_reports_with_and_without(
        self, tmp_path: Path, golden: tuple[Path, Path], capsys
    ) -> None:
        source = prepared(tmp_path, golden, {"q1": "correct", "q2": "correct", "q3": "correct"})
        ac.flag_exposed(argparse.Namespace(question_id="q1", reason="r", out=source))
        out = tmp_path / "m2.json"
        ac.reaudit_build(
            argparse.Namespace(source=source, out=out, min_days=0, seed=2, force=False)
        )
        meta = json.loads(out.read_text(encoding="utf-8"))
        for qid, label in {"q1": "correct", "q2": "correct", "q3": "partial"}.items():
            meta["labels"][qid]["label"] = label
        out.write_text(json.dumps(meta), encoding="utf-8")

        ac.reaudit_score(argparse.Namespace(out=out, also=[]))
        printed = capsys.readouterr().out
        assert "exact agreement 2/3" in printed
        assert "excluding 1 exposed row(s): 1/2" in printed


class TestQuestionAndKey:
    def test_reads_the_cache_when_the_row_is_null(self, tmp_path: Path) -> None:
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "rg-1.json").write_text(
            json.dumps({"questionSimple": "Does it trigger?", "answerSimple": "Yes."}),
            encoding="utf-8",
        )
        assert ac.question_and_key("rg-1", [cache], tmp_path) == ("Does it trigger?", "Yes.")

    def test_falls_back_to_the_inline_golden_row(self, tmp_path: Path) -> None:
        # Two pools feed this worksheet and they store text differently.
        # Assuming E-007's layout would silently produce an empty key for
        # half a batch.
        directory = tmp_path / "golden"
        write_jsonl(
            directory / "authored_v0.jsonl",
            # `stratum` is not decoration here: `load_questions` admits a row
            # only if it carries `stratum` or `gold_path`, and every real
            # golden row does. A row without one is invisible to the lookup,
            # which then raises rather than returning a blank key.
            [
                {
                    "id": "hand-1",
                    "stratum": "definition_1hop",
                    "question": "What does trample do?",
                    "answer": "Excess damage.",
                }
            ],
        )
        assert ac.question_and_key("hand-1", [tmp_path / "absent"], directory) == (
            "What does trample do?",
            "Excess damage.",
        )

    def test_refuses_when_the_key_is_nowhere(self, tmp_path: Path) -> None:
        # A blank key would be judged against nothing.
        (tmp_path / "golden").mkdir()
        with pytest.raises(SystemExit, match="rg-9"):
            ac.question_and_key("rg-9", [tmp_path / "absent"], tmp_path / "golden")


def open_second(tmp_path: Path, source: Path, name: str = "m2.json") -> Path:
    out = tmp_path / name
    ac.reaudit_build(
        argparse.Namespace(source=source, out=out, min_days=0, seed=2, force=False)
    )
    return out


class TestPooling:
    def build_batch(
        self, tmp_path: Path, golden: tuple[Path, Path], name: str, labels: dict[str, str]
    ) -> Path:
        """A frozen pass 1 and a fully-labelled pass 2, agreeing on all rows."""
        path = write_jsonl(tmp_path / f"{name}.jsonl", [answer(qid) for qid in labels])
        args = build_args(
            tmp_path, golden, [path], out=tmp_path / f"{name}_m1.json", batch=name
        )
        ac.build(args)
        first = json.loads(args.out.read_text(encoding="utf-8"))
        for qid, label in labels.items():
            first["labels"][qid]["label"] = label
        first["frozen"] = True
        first["frozen_at"] = date.today().isoformat()
        args.out.write_text(json.dumps(first), encoding="utf-8")

        out = tmp_path / f"{name}_m2.json"
        ac.reaudit_build(
            argparse.Namespace(source=args.out, out=out, min_days=0, seed=2, force=False)
        )
        second = json.loads(out.read_text(encoding="utf-8"))
        for qid, label in labels.items():
            second["labels"][qid]["label"] = label
        out.write_text(json.dumps(second), encoding="utf-8")
        return out

    def test_reports_each_batch_and_the_pool(
        self, tmp_path: Path, golden: tuple[Path, Path], capsys
    ) -> None:
        one = self.build_batch(tmp_path, golden, "b1", {"q1": "correct", "q2": "partial"})
        two = self.build_batch(tmp_path, golden, "b2", {"q3": "correct"})
        ac.reaudit_score(argparse.Namespace(out=one, also=[two]))
        printed = capsys.readouterr().out
        assert "batch b1" in printed
        assert "batch b2" in printed
        assert "pooled over 2 batch(es) (b1, b2): 3/3" in printed

    def test_refuses_to_pool_across_rubrics(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # Two passes under two rubrics are two instruments, and averaging
        # them is not a ceiling.
        one = self.build_batch(tmp_path, golden, "b1", {"q1": "correct"})
        two = self.build_batch(tmp_path, golden, "b2", {"q2": "correct"})
        meta = json.loads(two.read_text(encoding="utf-8"))
        meta["rubric_hash"] = "0" * 64
        two.write_text(json.dumps(meta), encoding="utf-8")
        with pytest.raises(SystemExit, match="different rubrics"):
            ac.reaudit_score(argparse.Namespace(out=one, also=[two]))


class TestWithholdMarginals:
    def test_status_hides_the_mix_while_a_second_pass_is_open(
        self, tmp_path: Path, golden: tuple[Path, Path], capsys
    ) -> None:
        # `show` was guarded and `status` was not, which left the aggregate
        # reachable by a command nobody thinks of as revealing.
        source = prepared(tmp_path, golden, {"q1": "correct", "q2": "incorrect"})
        open_second(tmp_path, source)
        ac.status(argparse.Namespace(out=source))
        printed = capsys.readouterr().out
        assert "label mix withheld" in printed
        assert "incorrect  " not in printed

    def test_status_shows_the_mix_when_no_second_pass_exists(
        self, tmp_path: Path, golden: tuple[Path, Path], capsys
    ) -> None:
        source = prepared(tmp_path, golden, {"q1": "correct", "q2": "incorrect"})
        ac.status(argparse.Namespace(out=source))
        assert "label mix withheld" not in capsys.readouterr().out


class TestOpenSecondPass:
    def test_found_by_relationship_not_by_filename(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # Tying the guard to one hard-coded path let any pair addressed
        # through --out slip past it — the guard naming a file instead of
        # the relationship it protects.
        source = prepared(tmp_path, golden, {"q1": "correct"})
        out = open_second(tmp_path, source, name="second-attempt.json")
        assert ac.open_second_pass(source) == out

    def test_none_once_the_second_pass_is_complete(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        source = prepared(tmp_path, golden, {"q1": "correct"})
        out = open_second(tmp_path, source)
        meta = json.loads(out.read_text(encoding="utf-8"))
        meta["labels"]["q1"]["label"] = "correct"
        out.write_text(json.dumps(meta), encoding="utf-8")
        assert ac.open_second_pass(source) is None

    def test_ignores_a_second_pass_over_a_different_worksheet(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        source = prepared(tmp_path, golden, {"q1": "correct"})
        stranger = tmp_path / "unrelated-m2.json"
        stranger.write_text(
            json.dumps({"source": str(tmp_path / "other.json"), "labels": {"q1": {"label": ""}}}),
            encoding="utf-8",
        )
        assert ac.open_second_pass(source) is None

    def test_survives_unrelated_json_in_the_directory(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        source = prepared(tmp_path, golden, {"q1": "correct"})
        (tmp_path / "notes.json").write_text("[1, 2, 3]", encoding="utf-8")
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
        assert ac.open_second_pass(source) is None


class TestGuardBlindness:
    def test_refuses_to_show_pass_one_while_pass_two_is_open(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        # Blindness is a property of what the tool will display, not a
        # promise the annotator makes to themself.
        source = prepared(tmp_path, golden, {"q1": "correct", "q2": "partial"})
        open_second(tmp_path, source)
        with pytest.raises(SystemExit, match="unlabelled row"):
            ac.guard_blindness(source, json.loads(source.read_text(encoding="utf-8")))

    def test_allows_it_once_pass_two_is_complete(
        self, tmp_path: Path, golden: tuple[Path, Path]
    ) -> None:
        source = prepared(tmp_path, golden, {"q1": "correct"})
        out = open_second(tmp_path, source)
        meta = json.loads(out.read_text(encoding="utf-8"))
        meta["labels"]["q1"]["label"] = "correct"
        out.write_text(json.dumps(meta), encoding="utf-8")
        ac.guard_blindness(source, json.loads(source.read_text(encoding="utf-8")))
