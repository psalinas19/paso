"""Real cases from Circuitos Eléctricos I in DC, correct and incorrect (SPEC 6.3).

Several tests here assert that a wrong step comes back *unverifiable* rather
than as an error. That is not the verifier giving up quietly: deciding whether
the currents at a node were summed correctly requires the circuit topology, and
structural recognition of diagrams is out of scope (SPEC 3). Those steps are the
model's job, and ADR 0004 counts them separately so the eval does not pretend
the symbolic verifier can catch them.
"""

from __future__ import annotations

import sympy

from app.schemas import StepKind as K
from app.schemas import StepRelation as R
from app.schemas import VerificationStatus
from app.verification.safe_parse import safe_parse
from tests.conftest import assert_correct, assert_error, mkstep, run, status_of

# --- Ohm, series and parallel ----------------------------------------------


def test_series_resistance_correct(circuitos):
    steps = [
        mkstep("s1", "Eq(R_1, 100)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(R_2, 220)", K.EQUATION, R.GIVEN),
        mkstep("s3", "Eq(R_eq, R_1 + R_2)", K.EQUATION, R.ASSERTION),
        mkstep("s4", "Eq(R_eq, 320)", K.EQUATION, R.SUBSTITUTION, ("s3",)),
    ]
    result = run(circuitos, steps)
    assert_correct(result, "s4")


def test_series_resistance_miscalculated(circuitos):
    steps = [
        mkstep("s1", "Eq(R_1, 100)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(R_2, 220)", K.EQUATION, R.GIVEN),
        mkstep("s3", "Eq(R_eq, R_1 + R_2)", K.EQUATION, R.ASSERTION),
        mkstep("s4", "Eq(R_eq, 230)", K.EQUATION, R.SUBSTITUTION, ("s3",)),
    ]
    result = run(circuitos, steps)
    assert_error(result, "s4")


def test_parallel_resistance_correct(circuitos):
    steps = [
        mkstep("s1", "Eq(R_1, 100)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(R_2, 100)", K.EQUATION, R.GIVEN),
        mkstep("s3", "Eq(R_eq, R_1*R_2/(R_1 + R_2))", K.EQUATION, R.ASSERTION),
        mkstep("s4", "Eq(R_eq, 50)", K.EQUATION, R.SUBSTITUTION, ("s3",)),
    ]
    result = run(circuitos, steps)
    assert_correct(result, "s4")


def test_parallel_combined_as_if_in_series_is_caught(circuitos):
    """Series/parallel confusion, caught because the arithmetic disagrees with
    the formula the student themselves wrote down."""
    steps = [
        mkstep("s1", "Eq(R_1, 100)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(R_2, 100)", K.EQUATION, R.GIVEN),
        mkstep("s3", "Eq(R_eq, R_1*R_2/(R_1 + R_2))", K.EQUATION, R.ASSERTION),
        mkstep("s4", "Eq(R_eq, 200)", K.EQUATION, R.SUBSTITUTION, ("s3",)),
    ]
    result = run(circuitos, steps)
    assert_error(result, "s4")


# --- voltage divider --------------------------------------------------------


def test_voltage_divider_correct(circuitos):
    steps = [
        mkstep("s1", "Eq(V_s, 12)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(R_1, 1000)", K.EQUATION, R.GIVEN),
        mkstep("s3", "Eq(R_2, 2000)", K.EQUATION, R.GIVEN),
        mkstep("s4", "Eq(V_2, V_s*R_2/(R_1 + R_2))", K.EQUATION, R.ASSERTION),
        mkstep("s5", "Eq(V_2, 8)", K.EQUATION, R.SUBSTITUTION, ("s4",)),
    ]
    result = run(circuitos, steps)
    assert_correct(result, "s5")


def test_voltage_divider_arithmetic_error_is_caught(circuitos):
    steps = [
        mkstep("s1", "Eq(V_s, 12)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(R_1, 1000)", K.EQUATION, R.GIVEN),
        mkstep("s3", "Eq(R_2, 2000)", K.EQUATION, R.GIVEN),
        mkstep("s4", "Eq(V_2, V_s*R_2/(R_1 + R_2))", K.EQUATION, R.ASSERTION),
        mkstep("s5", "Eq(V_2, 6)", K.EQUATION, R.SUBSTITUTION, ("s4",)),
    ]
    result = run(circuitos, steps)
    assert_error(result, "s5")


# --- nodal analysis ---------------------------------------------------------


def test_nodal_system_solved_correctly(circuitos):
    """2V1 - V2 = 10, -V1 + 3V2 = 5  ->  V1 = 7, V2 = 4."""
    steps = [
        mkstep(
            "s1",
            "[Eq(2*V_1 - V_2, 10), Eq(-V_1 + 3*V_2, 5)]",
            K.SYSTEM,
            R.ASSERTION,
        ),
        mkstep("s2", "[Eq(V_1, 7), Eq(V_2, 4)]", K.SYSTEM, R.EQUIVALENT, ("s1",)),
    ]
    result = run(circuitos, steps)
    assert_correct(result, "s2")


def test_nodal_system_solved_incorrectly_is_caught(circuitos):
    steps = [
        mkstep(
            "s1",
            "[Eq(2*V_1 - V_2, 10), Eq(-V_1 + 3*V_2, 5)]",
            K.SYSTEM,
            R.ASSERTION,
        ),
        mkstep("s2", "[Eq(V_1, 7), Eq(V_2, 5)]", K.SYSTEM, R.EQUIVALENT, ("s1",)),
    ]
    result = run(circuitos, steps)
    assert_error(result, "s2")


def test_a_stated_kcl_equation_is_unverifiable_not_correct(circuitos):
    """A KCL equation asserted from a diagram cannot be checked symbolically --
    there is no topology to check it against. It must come back as a warning,
    so the panel never implies the statement was verified."""
    steps = [
        mkstep(
            "s1",
            "[Eq(I_1 + I_2 - I_3, 0), Eq(I_1 - I_2 + I_3, 0)]",
            K.SYSTEM,
            R.ASSERTION,
        ),
    ]
    result = run(circuitos, steps)
    assert status_of(result, "s1") is VerificationStatus.UNVERIFIABLE


# --- the imaginary-unit collision, end to end ------------------------------


def test_currents_named_I_are_not_the_imaginary_unit(circuitos):
    """In DC there is no j, so I_1 and I_2 must stay ordinary currents (R3)."""
    parsed = safe_parse("Eq(I_1 + I_2, 3)", circuitos)
    assert sympy.I not in parsed.atoms()
    assert {s.name for s in parsed.free_symbols} == {"I_1", "I_2"}

    steps = [
        mkstep("s1", "Eq(I_1, 2)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(I_2, 1)", K.EQUATION, R.GIVEN),
        mkstep("s3", "Eq(I_3, I_1 + I_2)", K.EQUATION, R.ASSERTION),
        mkstep("s4", "Eq(I_3, 3)", K.EQUATION, R.SUBSTITUTION, ("s3",)),
    ]
    result = run(circuitos, steps)
    assert_correct(result, "s4")


# --- power ------------------------------------------------------------------


def test_power_computed_correctly(circuitos):
    steps = [
        mkstep("s1", "Eq(V_1, 12)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(I_1, 2)", K.EQUATION, R.GIVEN),
        mkstep("s3", "Eq(P, V_1*I_1)", K.EQUATION, R.ASSERTION),
        mkstep("s4", "Eq(P, 24)", K.EQUATION, R.SUBSTITUTION, ("s3",)),
    ]
    result = run(circuitos, steps)
    assert_correct(result, "s4")


def test_power_with_the_wrong_product_is_caught(circuitos):
    steps = [
        mkstep("s1", "Eq(V_1, 12)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(I_1, 2)", K.EQUATION, R.GIVEN),
        mkstep("s3", "Eq(P, V_1*I_1)", K.EQUATION, R.ASSERTION),
        mkstep("s4", "Eq(P, 14)", K.EQUATION, R.SUBSTITUTION, ("s3",)),
    ]
    result = run(circuitos, steps)
    assert_error(result, "s4")


# --- subject configuration drives the strategies (SPEC 12.5) ---------------


def test_a_subject_only_checks_what_its_config_enables(circuitos, ed):
    assert "system" in circuitos.strategies
    assert "ode" in ed.strategies
    # The same subject with systems switched off in its configuration.
    ed = ed.model_copy(update={"strategies": [s for s in ed.strategies if s != "system"]})

    steps = [
        mkstep("s1", "[Eq(2*V_1 - V_2, 10), Eq(-V_1 + 3*V_2, 5)]", K.SYSTEM, R.ASSERTION),
        mkstep("s2", "[Eq(V_1, 7), Eq(V_2, 5)]", K.SYSTEM, R.EQUIVALENT, ("s1",)),
    ]
    # Wrong either way, but only a subject with the strategy enabled can tell.
    assert status_of(run(circuitos, steps), "s2") is VerificationStatus.ERROR
    assert status_of(run(ed, steps), "s2") is VerificationStatus.UNVERIFIABLE
