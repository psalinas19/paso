"""Eval metrics (ADR 0004). No network: the provider is faked throughout."""

from __future__ import annotations

import json

import pytest
import yaml
from PIL import Image

from app.config import Settings
from app.eval import run_case
from app.evaluation.cases import CaseMeta, CaseTruth, EvalCase, TruthStep, load_cases
from app.evaluation.scoring import align, normalise_latex, score_case, steps_match, summarise
from app.llm.base import ProviderResult
from app.schemas import StepKind as K
from app.schemas import StepRelation as R
from app.schemas import Usage, VerificationStatus
from app.verification.runner import verify
from tests.conftest import mkstep


def truth_step(step_id, sympy_text, kind=K.EQUATION, relation=R.EQUIVALENT, **kw):
    return TruthStep(id=step_id, sympy=sympy_text, kind=kind, relation=relation, **kw)


# --- semantic matching, not textual ----------------------------------------


def test_equivalent_forms_count_as_the_same_reading(ed):
    """\\frac{1}{2} vs 0.5 is a formatting difference, not a misreading."""
    truth = truth_step("t1", "1/2", kind=K.EXPRESSION)
    predicted = mkstep("s1", "0.5", K.EXPRESSION, R.EQUIVALENT)
    assert steps_match(truth, predicted, ed)


def test_rearranged_equation_counts_as_the_same_reading(ed):
    truth = truth_step("t1", "Eq(2*x + 3, 7)")
    predicted = mkstep("s1", "Eq(2*x, 4)", K.EQUATION, R.EQUIVALENT)
    assert steps_match(truth, predicted, ed)


def test_a_genuinely_different_reading_does_not_match(ed):
    truth = truth_step("t1", "Eq(2*x + 3, 7)")
    predicted = mkstep("s1", "Eq(2*x - 3, 7)", K.EQUATION, R.EQUIVALENT)
    assert not steps_match(truth, predicted, ed)


def test_prose_steps_compare_by_normalised_latex(ed):
    truth = TruthStep(
        id="t1", latex=r"\text{Separando variables}", kind=K.TEXT, relation=R.ASSERTION
    )
    predicted = mkstep("s1", None, K.TEXT, R.ASSERTION, latex=r"\text{Separando  variables}")
    assert steps_match(truth, predicted, ed)


def test_reading_an_equation_as_prose_is_a_failure(ed):
    truth = truth_step("t1", "Eq(x, 1)")
    predicted = mkstep("s1", None, K.TEXT, R.ASSERTION, latex="x = 1")
    assert not steps_match(truth, predicted, ed)


def test_latex_normalisation_strips_formatting_only():
    assert normalise_latex(r"\left( x \right)") == "(x)"
    assert normalise_latex(r"a \cdot b") == "a*b"


# --- alignment --------------------------------------------------------------


def test_identical_sequences_align_one_to_one(ed):
    truth = [truth_step("t1", "Eq(x, 1)"), truth_step("t2", "Eq(x, 1)")]
    predicted = [
        mkstep("s1", "Eq(x, 1)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(x, 1)", K.EQUATION, R.EQUIVALENT),
    ]
    alignment = align(truth, predicted, ed)
    assert len(alignment.matched) == 2
    assert not alignment.missed and not alignment.invented


def test_a_missed_step_does_not_shift_everything_after_it(ed):
    """The reason alignment exists rather than zip: one omission must cost one
    step, not the whole page."""
    truth = [
        truth_step("t1", "Eq(x, 1)"),
        truth_step("t2", "Eq(x, 2)"),
        truth_step("t3", "Eq(x, 3)"),
    ]
    predicted = [
        mkstep("s1", "Eq(x, 1)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(x, 3)", K.EQUATION, R.EQUIVALENT),
    ]
    alignment = align(truth, predicted, ed)
    assert len(alignment.matched) == 2
    assert len(alignment.missed) == 1
    assert not alignment.invented


def test_an_invented_step_is_counted(ed):
    truth = [truth_step("t1", "Eq(x, 1)")]
    predicted = [
        mkstep("s1", "Eq(x, 1)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(x, 99)", K.EQUATION, R.EQUIVALENT),
    ]
    alignment = align(truth, predicted, ed)
    assert len(alignment.matched) == 1
    assert len(alignment.invented) == 1


# --- case scoring -----------------------------------------------------------


def _case(truth_steps) -> EvalCase:
    return EvalCase(
        meta=CaseMeta(id="test-01", subject="ed"),
        truth=CaseTruth(steps=truth_steps),
        image_path=__import__("pathlib").Path("unused.jpg"),
    )


def test_a_detected_seeded_error_counts_as_recall(ed):
    from app.evaluation.cases import SeededError

    truth = [
        truth_step("t1", "Eq(2*x + 3, 7)", relation=R.GIVEN),
        truth_step(
            "t2",
            "Eq(2*x, 10)",
            expected_status=VerificationStatus.ERROR,
            seeded_error=SeededError(type="sign", verifiable=True),
        ),
    ]
    predicted = [
        mkstep("s1", "Eq(2*x + 3, 7)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(2*x, 10)", K.EQUATION, R.EQUIVALENT, ("s1",)),
    ]
    verification = verify(ed, predicted, timeout_seconds=None)
    score = score_case(_case(truth), predicted, verification, ed)

    assert score.seeded_verifiable == 1
    assert score.seeded_detected == 1
    assert score.false_errors == 0


def test_a_false_error_is_counted_and_named(ed):
    """The metric that matters most: a correct step reported as wrong."""
    truth = [
        truth_step("t1", "Eq(2*x + 3, 7)", relation=R.GIVEN),
        truth_step("t2", "Eq(2*x, 4)"),
    ]
    predicted = [
        mkstep("s1", "Eq(2*x + 3, 7)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(2*x, 4)", K.EQUATION, R.EQUIVALENT, ("s1",)),
    ]
    verification = verify(ed, predicted, timeout_seconds=None)
    # Force a wrong verdict to prove the metric actually detects one.
    verification.by_id()["s2"].status = VerificationStatus.ERROR

    score = score_case(_case(truth), predicted, verification, ed)
    assert score.false_errors == 1
    assert any("FALSO ERROR" in note for note in score.notes)


def test_unverifiable_seeded_errors_are_excluded_not_held_against_us(ed):
    """A misstated KCL cannot be caught symbolically (SPEC 3), so counting it
    against the verifier would measure the wrong thing."""
    from app.evaluation.cases import SeededError

    truth = [
        truth_step(
            "t1",
            None,
            kind=K.DIAGRAM,
            relation=R.ASSERTION,
            expected_status=VerificationStatus.UNVERIFIABLE,
            seeded_error=SeededError(type="kcl", verifiable=False),
        ),
    ]
    predicted = [mkstep("s1", None, K.DIAGRAM, R.ASSERTION)]
    verification = verify(ed, predicted, timeout_seconds=None)
    score = score_case(_case(truth), predicted, verification, ed)

    assert score.seeded_verifiable == 0
    assert score.seeded_unverifiable_by_design == 1
    assert summarise([score]).seeded_recall == 1.0


def test_givens_are_excluded_from_the_warning_rate(ed):
    """Otherwise every piece of problem data inflates the unverifiable rate."""
    predicted = [
        mkstep("s1", "Eq(R_1, 10)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(R_2, 20)", K.EQUATION, R.GIVEN),
        mkstep("s3", None, K.TEXT, R.ASSERTION),
    ]
    truth = [truth_step("t1", "Eq(R_1, 10)", relation=R.GIVEN)]
    verification = verify(ed, predicted, timeout_seconds=None)
    score = score_case(_case(truth), predicted, verification, ed)

    assert score.scoreable_steps == 1  # only the text step
    assert score.unverifiable_steps == 1


# --- the bank, end to end ---------------------------------------------------


@pytest.fixture
def bank(tmp_path):
    """A one-case test bank on disk."""
    case_dir = tmp_path / "cases" / "ed-demo"
    case_dir.mkdir(parents=True)
    Image.new("RGB", (800, 600), "white").save(case_dir / "image.jpg")

    (case_dir / "meta.yaml").write_text(
        yaml.safe_dump(
            {"id": "ed-demo", "subject": "ed", "topic": "algebra", "source": "test"},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (case_dir / "truth.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "steps": [
                    {
                        "id": "t1",
                        "latex": "2x+3=7",
                        "sympy": "Eq(2*x + 3, 7)",
                        "kind": "equation",
                        "relation": "given",
                    },
                    {
                        "id": "t2",
                        "latex": "2x=4",
                        "sympy": "Eq(2*x, 4)",
                        "kind": "equation",
                        "relation": "equivalent",
                        "derives_from": ["t1"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path / "cases"


def test_cases_load_from_disk(bank):
    cases = load_cases(bank)
    assert len(cases) == 1
    assert cases[0].id == "ed-demo"
    assert cases[0].image_path.name == "image.jpg"


def test_full_case_run_scores_a_perfect_reading(bank, tmp_path, monkeypatch):
    monkeypatch.setattr("app.recognition.cache.CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr("app.llm.usage.USAGE_LOG", tmp_path / "usage.jsonl")

    class PerfectProvider:
        name, model = "fake", "fake-model"

        def extract_steps(self, image, system_prompt, instruction):
            return ProviderResult(
                steps=[
                    mkstep("s1", "Eq(2*x + 3, 7)", K.EQUATION, R.GIVEN),
                    mkstep("s2", "Eq(2*x, 4)", K.EQUATION, R.EQUIVALENT, ("s1",)),
                ],
                usage=Usage(endpoint="recognize", model="fake-model", cost_usd=0.02),
            )

    case = load_cases(bank)[0]
    settings = Settings(anthropic_api_key="test", recognition_cache_enabled=False)
    score = run_case(case, PerfectProvider(), settings, cache_only=False, use_cache=False)

    assert score.transcription_accuracy == 1.0
    assert score.is_clean
    assert score.false_errors == 0
    assert score.relation_matches == 2
