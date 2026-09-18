"""Numeric methods: recompute the iteration and compare within tolerance
(SPEC 6.3). Newton-Raphson, bisection, fixed point, and anything else written
as a chain of arithmetic.

Two things are checked:
  1. Internal consistency -- "x_2 = 1.5 - 0.25/3 = 1.4167" must actually come
     out to 1.4167. This is what catches a miscalculated iteration.
  2. Agreement with the previous step's formula, once earlier iterates are
     substituted in.

The tolerance is `hand_rounding` from the subject config, not machine epsilon:
the values were rounded by hand on paper, and flagging that as an error would
be a false cross.
"""

from __future__ import annotations

from typing import Any

import sympy

from app.schemas import Step, StepKind, StepRelation, StepVerification
from app.subjects.loader import NumericTolerance
from app.verification.registry import VerifyContext, register
from app.verification.strategies.base import (
    KindStrategy,
    correct,
    preceding,
    unverifiable,
    wrong,
)


def _as_list(obj: Any) -> list[Any]:
    return list(obj) if isinstance(obj, list) else [obj]


def numeric_values(step: Step, ctx: VerifyContext) -> dict[Any, Any]:
    """Iterates established earlier on the page, resolved in reading order so
    that x_2 can be expressed in terms of x_1."""
    values: dict[Any, Any] = {}
    for earlier in preceding(step, ctx):
        for item in _as_list(ctx.parsed_of(earlier.id)):
            if not isinstance(item, sympy.Equality) or not item.lhs.is_Symbol:
                continue
            try:
                rhs = sympy.simplify(item.rhs.subs(values))
            except Exception:  # noqa: BLE001
                continue
            if rhs.is_number and item.lhs not in values:
                values[item.lhs] = rhs
    return values


def _to_float(expr: Any) -> float | None:
    try:
        value = complex(expr.evalf())
    except (TypeError, ValueError, AttributeError):
        return None
    if value != value or abs(value) == float("inf"):
        return None
    if abs(value.imag) > 1e-9:
        return None
    return value.real


def _close(a: float, b: float, tol: NumericTolerance) -> bool:
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) <= max(tol.absolute, tol.hand_rounding * scale)


class NumericIterationStrategy(KindStrategy):
    name = "numeric_iteration"
    priority = 40
    kinds = frozenset({StepKind.NUMERIC_ITERATION})

    def verify(self, step: Step, ctx: VerifyContext) -> StepVerification:
        current = ctx.parsed_of(step.id)
        if current is None:
            return unverifiable(
                step, self.name, ctx.parse_errors.get(step.id, "el paso no se pudo interpretar")
            )

        if step.relation is StepRelation.ASSERTION:
            return unverifiable(
                step, self.name, "Afirmación nueva: no hay iteración previa con qué compararla."
            )

        values = numeric_values(step, ctx)
        tol = ctx.subject.tolerance
        checked = 0

        # 1. Each written equality must hold on its own terms.
        for equation in _as_list(current):
            if not isinstance(equation, sympy.Equality):
                continue
            left = _to_float(equation.lhs.subs(values))
            right = _to_float(equation.rhs.subs(values))
            if left is None or right is None:
                continue
            checked += 1
            if not _close(left, right, tol):
                return wrong(
                    step,
                    self.name,
                    f"La cuenta no da: el lado izquierdo vale {left:.6g} y el derecho {right:.6g}.",
                )

        # 2. And where the previous step gave a formula for the same quantity,
        #    the two must agree. Matching on the left-hand side matters: a
        #    parent that merely states x_0 = 1 says nothing about x_1, and
        #    comparing those right-hand sides positionally invents an error.
        formulas: dict[Any, Any] = {}
        for parent in ctx.parsed_parents(step):
            for parent_eq in _as_list(parent):
                if isinstance(parent_eq, sympy.Equality):
                    formulas.setdefault(parent_eq.lhs, parent_eq.rhs)

        for current_eq in _as_list(current):
            if not isinstance(current_eq, sympy.Equality):
                continue
            formula = formulas.get(current_eq.lhs)
            if formula is None:
                continue
            expected = _to_float(formula.subs(values))
            actual = _to_float(current_eq.rhs.subs(values))
            if expected is None or actual is None:
                continue
            checked += 1
            if not _close(expected, actual, tol):
                return wrong(
                    step,
                    self.name,
                    f"La iteración da {expected:.6g}, no {actual:.6g}.",
                )

        if checked == 0:
            return unverifiable(
                step,
                self.name,
                "No se pudo recalcular: faltan los valores numéricos de los pasos anteriores.",
            )

        return correct(
            step,
            self.name,
            f"La iteración se recalculó y coincide (tolerancia {tol.hand_rounding:g}).",
        )


register(NumericIterationStrategy())
