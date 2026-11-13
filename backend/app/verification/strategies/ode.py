"""Differential equations (SPEC 6.3).

A proposed solution is checked with checkodesol; rewriting the equation itself
(separating variables, multiplying by an integrating factor) is checked as an
ordinary equation equivalence.
"""

from __future__ import annotations

from typing import Any

import sympy
from sympy.core.function import AppliedUndef

from app.schemas import Step, StepKind
from app.subjects.loader import SubjectConfig
from app.verification.equivalence import Judgement, Outcome, equation_equivalence, satisfies
from app.verification.registry import VerifyContext, register
from app.verification.strategies.base import KindStrategy


def _is_differential(expr: Any) -> bool:
    return isinstance(expr, sympy.Basic) and bool(expr.atoms(sympy.Derivative))


def _unknown_function(expr: Any) -> Any | None:
    """The y(x) an ODE is solving for."""
    if not isinstance(expr, sympy.Basic):
        return None
    candidates = sorted(expr.atoms(AppliedUndef), key=lambda f: f.func.__name__)
    return candidates[0] if candidates else None


def check_ode_solution(ode: Any, solution: Any, subject: SubjectConfig) -> Judgement:
    """checkodesol, falling back to plain substitution when it cannot decide."""
    func = _unknown_function(ode)
    if func is None or not isinstance(solution, sympy.Equality):
        return satisfies(solution, ode, subject)

    try:
        ok, residual = sympy.checkodesol(ode, solution, func=func)
    except Exception as exc:  # noqa: BLE001 - checkodesol raises broadly
        fallback = satisfies(solution, ode, subject)
        if fallback.outcome is not Outcome.INCONCLUSIVE:
            return fallback
        return Judgement(Outcome.INCONCLUSIVE, "checkodesol", f"no se pudo comprobar: {exc}")

    if ok:
        return Judgement(Outcome.EQUIVALENT, "checkodesol", "la solución satisface la ecuación")

    # checkodesol returning False is not always conclusive: it can fail to
    # reduce a residual that is in fact zero. Confirm before calling it an error.
    fallback = satisfies(solution, ode, subject)
    if fallback.is_equivalent:
        return fallback
    if fallback.outcome is Outcome.DIFFERENT:
        return Judgement(
            Outcome.DIFFERENT,
            "checkodesol",
            f"al sustituir en la ecuación queda un residuo: {residual}",
        )
    return Judgement(
        Outcome.INCONCLUSIVE,
        "checkodesol",
        "checkodesol no pudo reducir el residuo; revísala a mano",
    )


class OdeStrategy(KindStrategy):
    name = "ode"
    # Ahead of `equation`, since an ODE is also an equation.
    priority = 40
    kinds = frozenset({StepKind.ODE})

    def compare(self, parent: Any, current: Any, subject: SubjectConfig) -> Judgement:
        # A non-differential step derived from a differential one is a proposed
        # solution, not an algebraic rewrite.
        if _is_differential(parent) and not _is_differential(current):
            return check_ode_solution(parent, current, subject)
        return equation_equivalence(parent, current, subject)

    def check_result(self, step: Step, ctx: VerifyContext, current: Any) -> Judgement:
        """The final solution is checked against the original ODE, not against
        whatever intermediate step happens to precede it.

        "Original" means the first differential equation the solution can be
        put into, with the problem data ahead of derived steps. Picking it by
        ancestry used to land on an intermediate line such as
        y' = -C1 sin x + C2 cos x, which a particular solution rightly does not
        satisfy for every C1 and C2.
        """
        odes = [
            target
            for target in self.result_targets(step, ctx)
            if _is_differential(target)
            and isinstance(current, sympy.Equality)
            and target.has(current.lhs)
        ]
        if not odes:
            return super().check_result(step, ctx, current)
        return check_ode_solution(odes[0], current, ctx.subject)


register(OdeStrategy())
