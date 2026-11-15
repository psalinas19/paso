"""Practice mode: what our code decides, with the model faked."""

from __future__ import annotations

from collections import Counter

from app.llm.base import ExerciseDraft, PracticeDraft
from app.schemas import StepKind as K
from app.schemas import StepRelation as R
from app.schemas import Usage, VerificationResult
from app.subjects.loader import load_subject
from app.tutor.practice import Weakness, attempt_outcome, build_practice, plan_slots
from app.verification.runner import verify
from tests.conftest import mkstep


def weakness(error_type, count, **more):
    return Weakness(
        error_type=error_type, label=error_type or "Sin clasificar", count=count, **more
    )


def planned(counts: dict, total: int) -> list:
    return [w.error_type for w in plan_slots([weakness(k, n) for k, n in counts.items()], total)]


def test_exercises_follow_how_often_each_mistake_was_made():
    assert planned({"sign": 6, "algebra": 2}, 4) == ["sign", "sign", "sign", "algebra"]
    assert planned({"algebra": 1, "sign": 1}, 4) == ["algebra", "algebra", "sign", "sign"]
    assert planned({"sign": 3}, 5) == ["sign"] * 5


def test_a_rare_mistake_is_not_crowded_out_by_rounding():
    # 5 : 2 : 1 over four exercises is 2.5, 1, 0.5; the spare one goes to the mistake with none.
    assert planned({"sign": 5, "algebra": 2, "units": 1}, 4) == [
        "sign",
        "sign",
        "algebra",
        "units",
    ]
    # More kinds of mistake than exercises: the most frequent ones get them.
    assert planned({"a": 4, "b": 3, "c": 2, "d": 1}, 3) == ["a", "b", "c"]


def test_nothing_to_practise_plans_nothing():
    assert plan_slots([], 4) == []
    assert plan_slots([weakness("sign", 0)], 4) == []


def status(*pairs) -> VerificationResult:
    return VerificationResult.model_validate(
        {
            "subject": "general",
            "steps": [
                {"step_id": i, "status": s, "detail": "", "method_used": "x"} for i, s in pairs
            ],
        }
    )


def test_an_attempt_is_judged_only_on_what_was_derived():
    given = mkstep("s1", "Eq(2*x, 6)", K.EQUATION, R.GIVEN)
    derived = mkstep("s2", "Eq(x, 3)", K.EQUATION, R.EQUIVALENT, ("s1",))
    last = mkstep("s3", "Eq(x, 3)", K.EQUATION, R.EQUIVALENT, ("s2",))

    assert attempt_outcome([given], status(("s1", "correct"))) is None
    assert attempt_outcome([given, derived], status(("s1", "correct"), ("s2", "correct"))) == (
        "passed"
    )
    mixed = status(("s1", "correct"), ("s2", "correct"), ("s3", "error"))
    assert attempt_outcome([given, derived, last], mixed) == "failed"
    # Nothing could be checked: neither a pass nor a failure.
    unsure = status(("s1", "unverifiable"), ("s2", "unverifiable"))
    assert attempt_outcome([given, derived], unsure) == "unchecked"


class Writer:
    name = "fake"
    model = "fake-model"

    def __init__(self, exercises):
        self.exercises = exercises
        self.instruction = ""

    def write_exercises(self, system_prompt, instruction):
        self.instruction = instruction
        return PracticeDraft(
            exercises=[
                ExerciseDraft(
                    slot=slot,
                    statement=statement,
                    data=[mkstep("g1", data, K.EQUATION, relation)],
                    answer=mkstep("r1", answer, K.EQUATION, R.GIVEN)
                    if answer
                    else mkstep("r1", None, K.TEXT, R.RESULT),
                )
                for slot, statement, data, answer, relation in self.exercises
            ],
            usage=Usage(endpoint="practice", model=self.model, cost_usd=0.03),
        )


def test_an_answer_is_only_trusted_after_the_verifier_proved_it():
    subject = load_subject("general")
    writer = Writer(
        [
            (1, "Resuelve $2x = 6$.", "Eq(2*x, 6)", "Eq(x, 3)", R.GIVEN),
            # The model marks its wrong answer as data, hoping it goes unchecked.
            (2, "Resuelve $2x = 8$.", "Eq(2*x, 8)", "Eq(x, 5)", R.GIVEN),
            (3, "Explica por qué $2x = 6$ tiene una sola solución.", "Eq(2*x, 6)", None, R.GIVEN),
            (3, "Un segundo ejercicio para el mismo número.", "Eq(x, 1)", "Eq(x, 1)", R.GIVEN),
            (9, "Un ejercicio que nadie pidió.", "Eq(x, 1)", "Eq(x, 1)", R.GIVEN),
            (4, "   ", "Eq(x, 1)", "Eq(x, 1)", R.GIVEN),
        ]
    )
    mistakes = [
        weakness("sign", 3, examples=[("x = 4", "No se sigue.")], topics=Counter({"despejes": 2})),
        weakness(None, 1, examples=[("y = 2", "")]),
    ]

    exercises, usage, prompt = build_practice(
        subject, mistakes, 4, writer, lambda steps: verify(subject, steps)
    )

    assert [e.statement[:12] for e in exercises] == ["Resuelve $2x", "Explica por "]
    solved, worded = exercises
    assert solved.answer_checked is True and solved.error_type == "sign"
    assert solved.topic == "despejes"
    # An answer in words cannot be proved: the exercise stays, its answer is never shown as checked.
    assert worded.answer_checked is False
    assert usage.cost_usd == 0.03 and prompt.version
    # Three exercises for the frequent mistake, one for the unclassified one.
    assert writer.instruction.count("(`sign`)") == 3
    assert "no clasificó" in writer.instruction and "latex: y = 2" in writer.instruction
