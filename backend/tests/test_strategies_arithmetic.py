"""Equalities with no unknowns. The first case is the one that got through on the
first real review: `5 + 5 = 12`, read as a given, came back as correct."""

from __future__ import annotations

import pytest

from app.schemas import StepKind as K
from app.schemas import StepRelation as R
from app.subjects.loader import load_subject
from tests.conftest import assert_correct, assert_error, assert_no_false_errors, mkstep, run


@pytest.fixture
def general():
    return load_subject("general")


def test_a_false_sum_is_an_error_even_as_a_given(general):
    result = run(general, [mkstep("s1", "Eq(5 + 5, 12)", K.EQUATION, R.GIVEN)])
    assert_error(result, "s1")
    assert "10" in result.by_id()["s1"].detail and "12" in result.by_id()["s1"].detail


def test_a_true_sum_is_correct_whatever_its_relation(general):
    result = run(
        general,
        [
            mkstep("s1", "Eq(5 + 5, 10)", K.EQUATION, R.GIVEN),
            mkstep("s2", "Eq(1/2 + 1/3, 5/6)", K.EQUATION, R.ASSERTION),
            mkstep("s3", "Eq(sqrt(16) * 2**3, 32)", K.EQUATION, R.ASSERTION),
            mkstep("s4", "Eq(Integral(x, (x, 0, 1)), 1/2)", K.EQUATION, R.ASSERTION),
        ],
    )
    assert_correct(result, "s1", "s2", "s3", "s4")


def test_each_link_of_a_chain_is_checked(general):
    # 2*3 = 6 = 7, transcribed pair by pair.
    result = run(general, [mkstep("s1", "[Eq(2*3, 6), Eq(6, 7)]", K.SYSTEM, R.GIVEN)])
    assert_error(result, "s1")


def test_rounding_by_hand_is_not_a_mistake(general):
    result = run(
        general,
        [
            mkstep("s1", "Eq(1/3, 0.33)", K.EQUATION, R.ASSERTION),  # rounded
            mkstep("s2", "Eq(2/3, 0.66)", K.EQUATION, R.ASSERTION),  # truncated
            mkstep("s3", "Eq(sqrt(2), 1.41)", K.EQUATION, R.ASSERTION),
            mkstep("s4", "Eq(0.1 + 0.2, 0.3)", K.EQUATION, R.ASSERTION),  # float noise
            mkstep("s5", "Eq(3.375 / 5, 0.675)", K.EQUATION, R.ASSERTION),
        ],
    )
    assert_no_false_errors(result, "s1", "s2", "s3", "s4", "s5")


def test_whole_numbers_get_no_rounding_allowance(general):
    # 0.5% of 500 would forgive this if the hand-rounding tolerance applied here.
    result = run(general, [mkstep("s1", "Eq(200 + 300, 501)", K.EQUATION, R.GIVEN)])
    assert_error(result, "s1")


def test_anything_with_an_unknown_is_left_to_the_other_strategies(general):
    result = run(
        general,
        [
            mkstep("s1", "Eq(2*x + 4, 10)", K.EQUATION, R.GIVEN),
            mkstep("s2", "Eq(x, 3)", K.EQUATION, R.EQUIVALENT, ("s1",)),
            mkstep("s3", "[Eq(V_1, 5), Eq(2 + 2, 4)]", K.SYSTEM, R.GIVEN),  # mixed: not ours
        ],
    )
    verdicts = result.by_id()
    assert verdicts["s1"].method_used == "given"
    assert verdicts["s2"].method_used != "arithmetic"
    assert verdicts["s3"].method_used == "given"
    assert_no_false_errors(result, "s1", "s2", "s3")
