"""Plain expressions: simplify(a - b) == 0, then numeric sampling (SPEC 6.3).

Derivatives and integrals are handled here rather than as their own kind: they
are operations inside an expression, detected from the tree (ADR 0003). An
unevaluated Derivative/Integral is evaluated with .doit() before comparing, so
"d/dx(x^2)" and "2x" compare equal while "d/dx(x^2)" and "3x" do not.
"""

from __future__ import annotations

from typing import Any

import sympy

from app.schemas import StepKind
from app.subjects.loader import SubjectConfig
from app.verification.equivalence import (
    Judgement,
    Outcome,
    as_difference,
    expr_equivalence,
)
from app.verification.registry import register
from app.verification.strategies.base import KindStrategy


def evaluate_operations(expr: Any) -> Any:
    """Carry out any written-but-unevaluated derivative or integral."""
    if not isinstance(expr, sympy.Basic):
        return expr
    if expr.atoms(sympy.Derivative) or expr.atoms(sympy.Integral):
        try:
            return expr.doit()
        except Exception:  # noqa: BLE001 - an integral SymPy cannot do stays as it is
            return expr
    return expr


def indefinite_integral_vars(expr: Any) -> set[Any]:
    """Variables integrated over without limits. SymPy writes an indefinite
    limit as a 1-tuple `(x,)` and a definite one as `(x, a, b)`."""
    if not isinstance(expr, sympy.Basic):
        return set()
    return {
        limit[0]
        for integral in expr.atoms(sympy.Integral)
        for limit in integral.limits
        if len(limit) == 1
    }


def integration_constant_judgement(parent: Any, current: Any) -> Judgement | None:
    """Handle the step right after an indefinite integral.

    `Integral(2*x, x).doit()` is `x**2`, with no constant, so comparing it
    against the student's correct `x**2 + C1` naively reports a difference of
    C1 and marks a right answer wrong. That is the false cross ADR 0004 forbids.

    Turning it around makes the check useful: after an indefinite integral the
    result *must* gain a constant, so a difference of exactly zero is the
    missing-constant error from SPEC 6.3.

    Returns None when this rule has nothing to say, so normal comparison runs.
    """
    integrated_over = indefinite_integral_vars(parent)
    if not integrated_over or not isinstance(current, sympy.Basic):
        return None

    try:
        evaluated = parent.doit()
    except Exception:  # noqa: BLE001
        return None
    if evaluated.atoms(sympy.Integral):
        return None  # SymPy could not solve it; not our call to make

    try:
        delta = sympy.simplify(as_difference(current) - as_difference(evaluated))
    except Exception:  # noqa: BLE001
        return None

    if delta == 0:
        return Judgement(
            Outcome.DIFFERENT,
            "integration-constant",
            "la integral es indefinida, así que falta la constante de integración.",
        )

    introduced = delta.free_symbols - parent.free_symbols
    all_new = bool(delta.free_symbols) and delta.free_symbols == introduced
    if all_new and not (introduced & integrated_over):
        name = ", ".join(sorted(s.name for s in introduced))
        return Judgement(
            Outcome.EQUIVALENT,
            "integration-constant",
            f"coincide, con la constante de integración {name}.",
        )

    return None


class ExpressionStrategy(KindStrategy):
    name = "expression"
    priority = 50
    kinds = frozenset({StepKind.EXPRESSION})

    def compare(self, parent: Any, current: Any, subject: SubjectConfig) -> Judgement:
        # Must run first: evaluating the integral below would otherwise report
        # the missing constant as an ordinary difference, and a correct answer
        # carrying +C1 as an error.
        constant = integration_constant_judgement(parent, current)
        if constant is not None:
            return constant

        direct = expr_equivalence(parent, current, subject)
        if direct.is_equivalent:
            return direct

        done = expr_equivalence(evaluate_operations(parent), evaluate_operations(current), subject)
        # Only upgrade the verdict: if evaluating settles it, use that; if not,
        # keep the more cautious of the two.
        if done.is_equivalent:
            return done
        return done if direct.outcome is Outcome.INCONCLUSIVE else direct


register(ExpressionStrategy())
