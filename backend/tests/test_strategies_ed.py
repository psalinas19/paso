"""Real cases from Ecuaciones Diferenciales, correct and incorrect (SPEC 6.3).

Every "correct" development here doubles as a false-cross regression test: the
target in ADR 0004 is zero errors reported on correct steps.
"""

from __future__ import annotations

from app.schemas import StepKind as K
from app.schemas import StepRelation as R
from app.schemas import VerificationStatus
from tests.conftest import (
    assert_correct,
    assert_error,
    assert_no_false_errors,
    mkstep,
    run,
    status_of,
)

# --- separable equation, done right ----------------------------------------


def test_separable_ode_solved_correctly(ed):
    """dy/dx = 2xy  ->  ln|y| = x^2 + C  ->  y = C1 e^(x^2)."""
    steps = [
        mkstep("s1", "Eq(Derivative(y(x), x), 2*x*y(x))", K.ODE, R.GIVEN),
        mkstep("s2", "Eq(Derivative(y(x), x)/y(x), 2*x)", K.ODE, R.EQUIVALENT, ("s1",)),
        mkstep("s3", "Eq(log(y(x)), x**2 + C1)", K.EQUATION, R.SPECIALIZATION, ("s2",)),
        mkstep("s4", "Eq(y(x), C1*exp(x**2))", K.ODE, R.RESULT, ("s1",)),
    ]
    result = run(ed, steps)
    assert_no_false_errors(result, "s1", "s2", "s3", "s4")
    assert_correct(result, "s1", "s4")


def test_sign_error_in_the_solution_is_caught(ed):
    """The classic: y = C1 e^(-x^2) does not satisfy y' = 2xy."""
    steps = [
        mkstep("s1", "Eq(Derivative(y(x), x), 2*x*y(x))", K.ODE, R.GIVEN),
        mkstep("s2", "Eq(y(x), C1*exp(-x**2))", K.ODE, R.RESULT, ("s1",)),
    ]
    result = run(ed, steps)
    assert_error(result, "s2")


# --- the integration constant (SPEC 6.3) -----------------------------------


def test_including_the_integration_constant_is_not_an_error(ed):
    """Regression: .doit() on an indefinite integral yields no constant, so a
    naive comparison marks this correct step wrong."""
    steps = [
        mkstep("s1", "Integral(2*x, x)", K.EXPRESSION, R.GIVEN),
        mkstep("s2", "x**2 + C1", K.EXPRESSION, R.EQUIVALENT, ("s1",)),
    ]
    result = run(ed, steps)
    assert_correct(result, "s2")


def test_missing_integration_constant_is_caught(ed):
    steps = [
        mkstep("s1", "Integral(2*x, x)", K.EXPRESSION, R.GIVEN),
        mkstep("s2", "x**2", K.EXPRESSION, R.EQUIVALENT, ("s1",)),
    ]
    result = run(ed, steps)
    assert_error(result, "s2")
    assert "constante de integración" in result.by_id()["s2"].detail


def test_missing_constant_on_both_sides_of_an_equation(ed):
    steps = [
        mkstep("s1", "Eq(Integral(1/y, y), Integral(2*x, x))", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(log(y), x**2)", K.EQUATION, R.EQUIVALENT, ("s1",)),
    ]
    result = run(ed, steps)
    assert_error(result, "s2")


def test_constant_present_on_an_equation_is_accepted(ed):
    steps = [
        mkstep("s1", "Eq(Integral(1/y, y), Integral(2*x, x))", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(log(y), x**2 + C1)", K.EQUATION, R.EQUIVALENT, ("s1",)),
    ]
    result = run(ed, steps)
    assert_correct(result, "s2")


# --- chain rule (SPEC 6.3) --------------------------------------------------


def test_chain_rule_applied_correctly(ed):
    steps = [
        mkstep("s1", "Derivative(sin(x**2), x)", K.EXPRESSION, R.GIVEN),
        mkstep("s2", "2*x*cos(x**2)", K.EXPRESSION, R.EQUIVALENT, ("s1",)),
    ]
    result = run(ed, steps)
    assert_correct(result, "s2")


def test_chain_rule_forgotten_is_caught(ed):
    """cos(x^2) instead of 2x cos(x^2): the inner derivative was dropped."""
    steps = [
        mkstep("s1", "Derivative(sin(x**2), x)", K.EXPRESSION, R.GIVEN),
        mkstep("s2", "cos(x**2)", K.EXPRESSION, R.EQUIVALENT, ("s1",)),
    ]
    result = run(ed, steps)
    assert_error(result, "s2")


# --- algebraic sign errors --------------------------------------------------


def test_sign_error_moving_a_term(ed):
    steps = [
        mkstep("s1", "Eq(2*x + 3, 7)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(2*x, 7 + 3)", K.EQUATION, R.EQUIVALENT, ("s1",)),
    ]
    result = run(ed, steps)
    assert_error(result, "s2")


def test_correct_term_move_is_accepted(ed):
    steps = [
        mkstep("s1", "Eq(2*x + 3, 7)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(2*x, 4)", K.EQUATION, R.EQUIVALENT, ("s1",)),
        mkstep("s3", "Eq(x, 2)", K.EQUATION, R.EQUIVALENT, ("s2",)),
    ]
    result = run(ed, steps)
    assert_correct(result, "s2", "s3")


def test_multiplying_both_sides_by_a_constant_is_not_an_error(ed):
    """An equation times a nonzero constant is the same equation. Comparing
    equations as plain expressions would flag this."""
    steps = [
        mkstep("s1", "Eq(x/2 + 1, 3)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(x + 2, 6)", K.EQUATION, R.EQUIVALENT, ("s1",)),
    ]
    result = run(ed, steps)
    assert_correct(result, "s2")
    assert result.by_id()["s2"].method_used == "proportional"


# --- initial conditions: the case that breaks "compare with the previous" ---


def test_applying_an_initial_condition_is_not_an_error(ed):
    """y = C1 e^x with y(0) = 3 becomes y = 3 e^x. That is a specialization,
    not an equivalence, and must not be marked wrong (ADR 0003, R1)."""
    steps = [
        mkstep("s1", "Eq(Derivative(y(x), x), y(x))", K.ODE, R.GIVEN),
        mkstep("s2", "Eq(y(x), C1*exp(x))", K.ODE, R.EQUIVALENT, ("s1",)),
        mkstep("s3", "Eq(y(x), 3*exp(x))", K.ODE, R.SPECIALIZATION, ("s2",)),
    ]
    result = run(ed, steps)
    assert_no_false_errors(result, "s2", "s3")


def test_a_given_is_never_flagged(ed):
    steps = [mkstep("s1", "Eq(y(0), 3)", K.EQUATION, R.GIVEN)]
    result = run(ed, steps)
    assert_correct(result, "s1")
    assert result.by_id()["s1"].method_used == "given"


# --- numeric iteration (SPEC 6.3) ------------------------------------------


def test_newton_raphson_iteration_correct(ed):
    """x0 = 1, f(x) = x^2 - 2  ->  x1 = 1 - (1-2)/2 = 1.5."""
    steps = [
        mkstep("s1", "Eq(x_0, 1)", K.NUMERIC_ITERATION, R.GIVEN),
        mkstep(
            "s2",
            "[Eq(x_1, x_0 - (x_0**2 - 2)/(2*x_0)), Eq(x_0 - (x_0**2 - 2)/(2*x_0), 1.5)]",
            K.NUMERIC_ITERATION,
            R.SUBSTITUTION,
            ("s1",),
        ),
    ]
    result = run(ed, steps)
    assert_correct(result, "s2")


def test_miscalculated_iteration_is_caught(ed):
    """Same setup, but the student writes 1.25."""
    steps = [
        mkstep("s1", "Eq(x_0, 1)", K.NUMERIC_ITERATION, R.GIVEN),
        mkstep(
            "s2",
            "[Eq(x_1, x_0 - (x_0**2 - 2)/(2*x_0)), Eq(x_0 - (x_0**2 - 2)/(2*x_0), 1.25)]",
            K.NUMERIC_ITERATION,
            R.SUBSTITUTION,
            ("s1",),
        ),
    ]
    result = run(ed, steps)
    assert_error(result, "s2")


def test_hand_rounding_is_tolerated(ed):
    """1.41667 written for 1.416666... is not a mistake."""
    steps = [
        mkstep("s1", "Eq(x_1, 1.5)", K.NUMERIC_ITERATION, R.GIVEN),
        mkstep(
            "s2",
            "[Eq(x_2, x_1 - (x_1**2 - 2)/(2*x_1)), Eq(x_1 - (x_1**2 - 2)/(2*x_1), 1.41667)]",
            K.NUMERIC_ITERATION,
            R.SUBSTITUTION,
            ("s1",),
        ),
    ]
    result = run(ed, steps)
    assert_correct(result, "s2")


# --- error propagation (ADR 0003, R2) --------------------------------------


def test_one_mistake_produces_exactly_one_cross(ed):
    """After a wrong step, consistent steps stay correct but are tagged with the
    step that actually went wrong, instead of turning the whole page red."""
    steps = [
        mkstep("s1", "Eq(2*x + 3, 7)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(2*x, 10)", K.EQUATION, R.EQUIVALENT, ("s1",)),  # wrong: +3
        mkstep("s3", "Eq(x, 5)", K.EQUATION, R.EQUIVALENT, ("s2",)),  # right, given s2
    ]
    result = run(ed, steps)

    assert result.count(VerificationStatus.ERROR) == 1
    assert_error(result, "s2")
    assert status_of(result, "s3") is VerificationStatus.CORRECT
    assert result.by_id()["s3"].depends_on_error == "s2"
    assert "tiene un error" in result.by_id()["s3"].detail


def test_taint_flows_through_a_chain(ed):
    steps = [
        mkstep("s1", "Eq(2*x + 3, 7)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(2*x, 10)", K.EQUATION, R.EQUIVALENT, ("s1",)),
        mkstep("s3", "Eq(x, 5)", K.EQUATION, R.EQUIVALENT, ("s2",)),
        mkstep("s4", "Eq(x + 1, 6)", K.EQUATION, R.EQUIVALENT, ("s3",)),
    ]
    result = run(ed, steps)
    assert result.count(VerificationStatus.ERROR) == 1
    assert result.by_id()["s4"].depends_on_error == "s2"


# --- things that must stay unverifiable, never errors ----------------------


def test_illegible_step_is_unverifiable(ed):
    steps = [mkstep("s1", None, K.EXPRESSION, R.EQUIVALENT, legible=False)]
    result = run(ed, steps)
    assert status_of(result, "s1") is VerificationStatus.UNVERIFIABLE


def test_prose_step_is_unverifiable(ed):
    steps = [mkstep("s1", None, K.TEXT, R.ASSERTION, latex=r"\text{Separando variables}")]
    result = run(ed, steps)
    assert status_of(result, "s1") is VerificationStatus.UNVERIFIABLE


def test_unparseable_expression_is_unverifiable_not_an_error(ed):
    """A dialect violation is our failure, not the student's (ADR 0002)."""
    steps = [
        mkstep("s1", "Eq(x, 1)", K.EQUATION, R.GIVEN),
        mkstep("s2", "x === 1", K.EQUATION, R.EQUIVALENT, ("s1",)),
    ]
    result = run(ed, steps)
    assert status_of(result, "s2") is VerificationStatus.UNVERIFIABLE


def test_step_without_a_parent_is_unverifiable(ed):
    steps = [mkstep("s1", "Eq(x, 1)", K.EQUATION, R.EQUIVALENT)]
    result = run(ed, steps)
    assert status_of(result, "s1") is VerificationStatus.UNVERIFIABLE
