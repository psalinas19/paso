"""The tutor's pure functions on the case that started them: a page with only
the problem on it. Model faked; verifier real, in process."""

from __future__ import annotations

import pytest

from app.llm.base import SolutionDraft
from app.schemas import StepKind as K
from app.schemas import StepRelation as R
from app.schemas import Usage
from app.subjects.loader import load_subject
from app.tutor.explain import build_instruction
from app.tutor.hint import build_hint
from app.tutor.solve import NothingToSolveError, build_solution, problem_data
from tests.conftest import mkstep, run


class Solver:
    name, model = "fake", "fake-model"

    def __init__(self, steps):
        self.steps = steps
        self.instruction = ""

    def solve(self, system_prompt, instruction, image):
        del system_prompt, image
        self.instruction = instruction
        return SolutionDraft(
            goal="Despejar x.",
            method="Operaciones inversas.",
            steps=list(self.steps),
            whys={},
            answer="$x = 7/3$",
            check="",
            usage=Usage(endpoint="solve", model=self.model, cost_usd=0.01),
        )

    def write_hint(self, *args):
        raise AssertionError("no call is needed when there is nothing to hint about")


@pytest.fixture
def general():
    return load_subject("general")


def only_statement():
    return [mkstep("s1", "Eq(3*x + 2, 9)", K.EQUATION, R.GIVEN, latex="3x + 2 = 9")]


def test_only_a_statement_is_not_reported_as_everything_correct(general):
    steps = only_statement()

    hint, usage = build_hint(general, steps, run(general, steps), Solver([]))

    assert usage is None
    assert "Solo está el enunciado" in hint.verified
    assert "no encontró errores" not in hint.verified
    # And the tutor is told there is no development yet, so it says what to do next.
    assert "todavía no hay desarrollo" in build_instruction(steps, run(general, steps), None)


def test_a_lone_equation_is_solved_and_every_step_proved(general):
    steps = only_statement()
    solver = Solver(
        [
            mkstep("r1", "Eq(3*x, 7)", K.EQUATION, R.EQUIVALENT, ("g1",)),
            mkstep("r2", "Eq(x, 7/3)", K.EQUATION, R.RESULT, ("r1",)),
        ]
    )

    solution, usages = build_solution(
        general, steps, run(general, steps), solver, lambda s: run(general, s)
    )

    assert solution.verified and solution.checked_steps == 2 and len(usages) == 1
    assert [s.step.id for s in solution.steps] == ["g1", "r1", "r2"]
    assert "g1 | latex: 3x + 2 = 9" in solver.instruction


def test_a_step_in_words_does_not_spoil_a_proved_solution(general):
    steps = only_statement()
    solver = Solver(
        [
            mkstep("r1", None, K.TEXT, R.ASSERTION, latex="\\text{Restamos 2}"),
            mkstep("r2", "Eq(3*x, 7)", K.EQUATION, R.EQUIVALENT, ("g1",)),
            mkstep("r3", "Eq(x, 7/3)", K.EQUATION, R.RESULT, ("r2",)),
        ]
    )

    solution, _ = build_solution(
        general, steps, run(general, steps), solver, lambda s: run(general, s)
    )

    assert solution.verified and solution.unchecked_steps == 0


def test_a_formula_nobody_could_check_means_no_badge(general):
    steps = only_statement()
    # A formula the verifier cannot parse: it must not count as proved.
    solver = Solver([mkstep("r1", "Eq(x, ", K.EQUATION, R.RESULT, ("g1",))])

    solution, _ = build_solution(
        general, steps, run(general, steps), solver, lambda s: run(general, s)
    )

    assert not solution.verified and solution.unchecked_steps == 1


def test_the_first_line_is_the_problem_when_nothing_is_marked_as_data():
    steps = [
        mkstep("s1", "Eq(3*x + 2, 9)", K.EQUATION, R.ASSERTION),
        mkstep("s2", "Eq(3*x, 7)", K.EQUATION, R.EQUIVALENT, ("s1",)),
    ]
    [data] = problem_data(steps)
    assert (data.id, data.relation, data.sympy) == ("g1", R.GIVEN, "Eq(3*x + 2, 9)")

    # A statement the dialect cannot express is still the problem to solve.
    [words] = problem_data([mkstep("s1", None, K.TEXT, R.ASSERTION, latex="hola")])
    assert (words.id, words.relation, words.sympy) == ("g1", R.GIVEN, None)

    with pytest.raises(NothingToSolveError):
        problem_data([mkstep("s1", None, K.TEXT, R.ASSERTION, latex="?", legible=False)])


def test_a_statement_without_formulas_gets_a_solution_but_no_badge(general):
    steps = [mkstep("s1", None, K.EXPRESSION, R.GIVEN, latex="\\mathcal{L}^{-1}\\{ ... \\}")]
    solver = Solver([mkstep("r1", "Eq(f(t), sin(3*t))", K.EQUATION, R.RESULT, ("g1",))])

    solution, _ = build_solution(
        general, steps, run(general, steps), solver, lambda s: run(general, s)
    )

    # Nothing anchors it to the page, so it is shown, and shown as unverified.
    assert [s.step.id for s in solution.steps] == ["g1", "r1"]
    assert not solution.verified and solution.wrong_steps == 0


def test_an_inverse_laplace_transform_is_solved_and_proved(general):
    steps = [mkstep("s1", "InverseLaplaceTransform(1/(s*(s + 1)), s, t)", K.EXPRESSION, R.GIVEN)]
    solver = Solver(
        [
            mkstep(
                "r1",
                "InverseLaplaceTransform(1/s - 1/(s + 1), s, t)",
                K.EXPRESSION,
                R.EQUIVALENT,
                ("g1",),
            ),
            mkstep("r2", "1 - exp(-t)", K.EXPRESSION, R.RESULT, ("r1",)),
        ]
    )

    solution, _ = build_solution(
        general, steps, run(general, steps), solver, lambda s: run(general, s)
    )

    assert solution.verified and solution.checked_steps == 2

    solver.steps[1] = mkstep("r2", "1 + exp(-t)", K.EXPRESSION, R.RESULT, ("r1",))
    wrong, usages = build_solution(
        general, steps, run(general, steps), solver, lambda s: run(general, s)
    )
    assert not wrong.verified and wrong.wrong_steps == 1 and len(usages) == 2
