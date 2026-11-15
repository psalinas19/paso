"""Graphing (SPEC 6.10): what can be drawn, and saying no when it cannot."""

from __future__ import annotations

import math

import pytest

from app.plotting import plot_of
from app.schemas import StepKind as K
from app.schemas import StepRelation as R
from app.subjects.loader import load_subject
from tests.conftest import mkstep

GENERAL = load_subject("general")


def plot(text: str, kind=K.EQUATION):
    return plot_of(GENERAL, [mkstep("s1", text, kind, R.GIVEN)])


def value(tree, x: float) -> float:
    """A reference evaluator, written independently of the notebook's."""
    if "n" in tree:
        return tree["n"]
    if "v" in tree:
        return x
    args = [value(a, x) for a in tree["args"]]
    if tree.get("op") == "+":
        return sum(args)
    if tree.get("op") == "*":
        return math.prod(args)
    if tree.get("op") == "^":
        return args[0] ** args[1]
    return {"sin": math.sin, "cos": math.cos, "exp": math.exp, "log": math.log, "abs": abs}[
        tree["f"]
    ](args[0])


@pytest.mark.parametrize(
    ("text", "label", "variable", "at", "expected"),
    [
        ("Eq(y, x**2 - 3*x + 2)", "y", "x", 4.0, 6.0),
        ("Eq(3*exp(-2*t)*cos(4*t), y(t))", "y{\\left(t \\right)}", "t", 0.0, 3.0),
        ("sin(x)/x", "y", "x", math.pi / 2, 2 / math.pi),
        ("Eq(f(x), sqrt(x) + Abs(x - 5))", "f{\\left(x \\right)}", "x", 4.0, 3.0),
        ("Eq(y, Derivative(x**3, x))", "y", "x", 2.0, 12.0),
        ("Eq(y, 7)", "y", "x", 123.0, 7.0),
        ("Eq(v, log(s) + pi)", "v", "s", 1.0, math.pi),
    ],
)
def test_a_function_of_one_variable_becomes_a_tree_that_evaluates_to_it(
    text, label, variable, at, expected
):
    found = plot(text)

    assert found["plottable"] is True, found
    assert (found["label"], found["variable"]) == (label, variable)
    assert value(found["tree"], at) == pytest.approx(expected)
    assert found["latex"] == text  # mkstep writes the SymPy text as LaTeX


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("Eq(x**2 + y**2, 1)", "no está despejada"),
        ("Eq(y, x*y + 1)", "no está despejada"),
        ("Eq(y, a*x + b)", "más de una variable (a, b, x)"),
        ("Eq(y, Integral(exp(-x**2), x))", "Integral"),
        ("Eq(y, sqrt(-1)*x)", "complejos"),
        ("Gt(x, 3)", "Gt"),
        ("Eq(x, 4)", "es el valor de x"),
        ("Eq(3, t)", "es el valor de t"),
        ("Eq(y, LaplaceTransform(exp(-2*t), t, s))", "LaplaceTransform"),
        ("().__class__", "no pude interpretar"),
    ],
)
def test_what_cannot_be_drawn_is_refused_with_the_reason(text, why):
    found = plot(text)

    assert found["plottable"] is False
    assert why in found["reason"]
    assert "tree" not in found


def test_the_first_drawable_line_of_the_selection_is_the_one_drawn():
    steps = [
        mkstep("s1", None, K.TEXT, R.GIVEN),
        mkstep("s2", "Eq(x**2 + y**2, 1)", K.EQUATION, R.GIVEN),
        mkstep("s3", "Eq(y, 2*x)", K.EQUATION, R.EQUIVALENT, ("s2",)),
    ]
    found = plot_of(GENERAL, steps)
    assert found["plottable"] is True and found["latex"] == "Eq(y, 2*x)"

    nothing = plot_of(GENERAL, steps[:1])
    assert nothing == {
        "plottable": False,
        "reason": "no encontré una ecuación legible en la selección",
    }
    # With nothing drawable, the reason given is the first equation's.
    assert "no está despejada" in plot_of(GENERAL, steps[:2])["reason"]


def test_a_very_long_expression_is_refused_rather_than_shipped():
    long = " + ".join(f"sin({n}*x)" for n in range(1, 200))
    assert "demasiado larga" in plot(f"Eq(y, {long})")["reason"]
