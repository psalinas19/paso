"""Equivalence predicates shared by the strategies (SPEC 6.3).

Every predicate returns an Outcome rather than a bool, because "I could not
decide" is a distinct and very common answer that must reach the user as a
warning and never as an error. See ADR 0004: a false error is the worst failure
this app can produce.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import sympy
from sympy.core.function import AppliedUndef

from app.subjects.loader import SubjectConfig

#: Points sampled when simplify() cannot decide (SPEC 6.3).
NUMERIC_SAMPLES = 10
#: Sampling range, kept away from 0 to dodge the most common poles.
SAMPLE_RANGE = (-7.0, 7.0)


class Outcome(StrEnum):
    EQUIVALENT = "equivalent"
    DIFFERENT = "different"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class Judgement:
    outcome: Outcome
    method: str
    detail: str = ""

    @property
    def is_equivalent(self) -> bool:
        return self.outcome is Outcome.EQUIVALENT


def _is_symbolic_opaque(expr: Any) -> bool:
    """Whether numeric sampling is meaningless for this expression.

    Undefined functions (y(x)), unevaluated derivatives and unevaluated
    integrals have no numeric value, so sampling them would compare nothing.
    """
    if not isinstance(expr, sympy.Basic):
        return True
    return bool(
        expr.atoms(AppliedUndef) or expr.atoms(sympy.Derivative) or expr.atoms(sympy.Integral)
    )


def _sample_numerically(diff: sympy.Basic, seed: int = 0) -> Judgement:
    """Evaluate `diff` at random points; it should be 0 everywhere."""
    symbols = sorted(diff.free_symbols, key=lambda s: s.name)
    if not symbols:
        try:
            value = complex(diff.evalf())
        except (TypeError, ValueError):
            return Judgement(Outcome.INCONCLUSIVE, "numeric", "no se pudo evaluar")
        if abs(value) < 1e-9:
            return Judgement(Outcome.EQUIVALENT, "numeric")
        return Judgement(Outcome.DIFFERENT, "numeric", f"difieren en {value:.4g}")

    rng = random.Random(seed)
    checked = 0
    for _ in range(NUMERIC_SAMPLES * 4):
        if checked >= NUMERIC_SAMPLES:
            break
        point = {s: sympy.Float(rng.uniform(*SAMPLE_RANGE)) for s in symbols}
        try:
            value = complex(diff.subs(point).evalf())
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if value != value or abs(value) == float("inf"):  # NaN or a pole
            continue
        checked += 1
        if abs(value) > 1e-6:
            pretty = ", ".join(f"{s}={float(v):.3g}" for s, v in point.items())
            return Judgement(
                Outcome.DIFFERENT,
                "numeric",
                f"difieren al evaluar en {pretty}",
            )

    if checked == 0:
        return Judgement(Outcome.INCONCLUSIVE, "numeric", "no se pudo evaluar en ningún punto")
    return Judgement(
        Outcome.EQUIVALENT,
        "numeric",
        f"coinciden en {checked} puntos evaluados",
    )


def expr_equivalence(a: Any, b: Any, subject: SubjectConfig) -> Judgement:
    """simplify(a - b) == 0, falling back to numeric sampling (SPEC 6.3)."""
    del subject  # reserved: assumptions may become subject-specific

    if not isinstance(a, sympy.Basic) or not isinstance(b, sympy.Basic):
        return Judgement(Outcome.INCONCLUSIVE, "simplify", "no son expresiones comparables")

    if a == b:
        return Judgement(Outcome.EQUIVALENT, "structural")

    try:
        diff = sympy.simplify(a - b)
    except Exception as exc:  # noqa: BLE001 - SymPy raises many things
        return Judgement(Outcome.INCONCLUSIVE, "simplify", f"simplify falló: {exc}")

    if diff == 0:
        return Judgement(Outcome.EQUIVALENT, "simplify")

    # A nonzero *number* is a definite difference; a nonzero expression may just
    # be something simplify could not fold, so that case falls through.
    if diff.is_number:
        try:
            if abs(complex(diff.evalf())) > 1e-9:
                return Judgement(Outcome.DIFFERENT, "simplify", f"la diferencia es {diff}")
        except (TypeError, ValueError):
            pass

    if _is_symbolic_opaque(diff):
        return Judgement(
            Outcome.INCONCLUSIVE,
            "simplify",
            "queda una diferencia que no se pudo reducir ni evaluar",
        )

    return _sample_numerically(diff)


def as_difference(eq: Any) -> Any:
    """Eq(l, r) -> l - r; anything else is returned unchanged."""
    if isinstance(eq, sympy.Equality):
        return eq.lhs - eq.rhs
    return eq


def equation_equivalence(a: Any, b: Any, subject: SubjectConfig) -> Judgement:
    """Same solution set, or (lhs - rhs) proportional by a nonzero factor."""
    da, db = as_difference(a), as_difference(b)

    if not isinstance(da, sympy.Basic) or not isinstance(db, sympy.Basic):
        return Judgement(Outcome.INCONCLUSIVE, "equation", "no son ecuaciones comparables")

    direct = expr_equivalence(da, db, subject)
    if direct.is_equivalent:
        return Judgement(Outcome.EQUIVALENT, direct.method, direct.detail)

    # Multiplying both sides by a nonzero constant keeps the equation. This is
    # why equations cannot be compared as plain expressions.
    if db != 0:
        try:
            ratio = sympy.simplify(da / db)
            if ratio.is_number and ratio != 0 and ratio.is_finite:
                return Judgement(
                    Outcome.EQUIVALENT,
                    "proportional",
                    f"la misma ecuación multiplicada por {ratio}",
                )
        except Exception:  # noqa: BLE001
            pass

    if direct.outcome is Outcome.DIFFERENT:
        return Judgement(Outcome.DIFFERENT, direct.method, direct.detail)
    return Judgement(Outcome.INCONCLUSIVE, "equation", direct.detail)


def satisfies(candidate: Any, equation: Any, subject: SubjectConfig) -> Judgement:
    """Whether substituting `candidate` into `equation` closes it.

    `candidate` is an Eq assigning a symbol or function, e.g. Eq(y(x), ...) or
    Eq(V_1, 10); `equation` is the relation it should satisfy.
    """
    if not isinstance(candidate, sympy.Equality) or not isinstance(equation, sympy.Basic):
        return Judgement(Outcome.INCONCLUSIVE, "substitute", "no se pudo sustituir")

    target = as_difference(equation)
    try:
        substituted = target.subs(candidate.lhs, candidate.rhs)
        residual = sympy.simplify(substituted.doit())
    except Exception as exc:  # noqa: BLE001
        return Judgement(Outcome.INCONCLUSIVE, "substitute", f"la sustitución falló: {exc}")

    if residual == 0:
        return Judgement(Outcome.EQUIVALENT, "substitute", "la sustitución cierra la ecuación")

    if _is_symbolic_opaque(residual):
        return Judgement(Outcome.INCONCLUSIVE, "substitute", "quedó un residuo no reducible")

    sampled = _sample_numerically(residual)
    return Judgement(sampled.outcome, "substitute", sampled.detail)


def specializes(parent: Any, current: Any, subject: SubjectConfig) -> Judgement:
    """Whether `current` is `parent` with its free constants pinned down.

    Applying y(0) = 3 to y = C1 e^x gives y = 3 e^x. That is not an equivalence
    -- substituting blindly leaves (3 - C1)e^x and looks like an error -- so the
    question to ask is whether some value of C1 makes the two agree (ADR 0003).
    """
    pd, cd = as_difference(parent), as_difference(current)
    if not isinstance(pd, sympy.Basic) or not isinstance(cd, sympy.Basic):
        return Judgement(Outcome.INCONCLUSIVE, "specialize", "no se pudieron comparar")

    try:
        delta = sympy.simplify(pd - cd)
    except Exception as exc:  # noqa: BLE001
        return Judgement(Outcome.INCONCLUSIVE, "specialize", f"simplify falló: {exc}")

    if delta == 0:
        return Judgement(Outcome.EQUIVALENT, "specialize", "coincide con el paso anterior")

    # The constants being fixed are what the parent has and the current lacks.
    unknowns = sorted(pd.free_symbols - cd.free_symbols, key=lambda s: s.name)
    if not unknowns:
        return Judgement(Outcome.INCONCLUSIVE, "specialize", "no hay constante que fijar")

    try:
        solutions = sympy.solve(delta, unknowns, dict=True)
    except Exception as exc:  # noqa: BLE001
        return Judgement(Outcome.INCONCLUSIVE, "specialize", f"solve falló: {exc}")

    for solution in solutions:
        # A constant has to be constant: a "solution" that still depends on the
        # variables of the step is not a specialization, it is a different answer.
        if all(
            value.is_number or not (value.free_symbols & cd.free_symbols)
            for value in solution.values()
        ):
            fixed = ", ".join(f"{k} = {v}" for k, v in solution.items())
            return Judgement(Outcome.EQUIVALENT, "specialize", f"es el paso anterior con {fixed}")

    return Judgement(
        Outcome.DIFFERENT,
        "specialize",
        "no existe un valor de la constante que haga coincidir los dos pasos",
    )


def solution_sets_match(a: Any, b: Any, unknowns: list[sympy.Symbol]) -> Judgement:
    """Whether two systems of equations have the same solution (SPEC 6.3)."""
    try:
        sol_a = sympy.solve(a, unknowns, dict=True)
        sol_b = sympy.solve(b, unknowns, dict=True)
    except Exception as exc:  # noqa: BLE001
        return Judgement(Outcome.INCONCLUSIVE, "solve", f"solve falló: {exc}")

    if not sol_a or not sol_b:
        return Judgement(Outcome.INCONCLUSIVE, "solve", "el sistema no tuvo solución única")

    def normalise(solutions: list[dict]) -> set[frozenset[tuple[str, Any]]]:
        out = set()
        for sol in solutions:
            out.add(
                frozenset(
                    (str(k), sympy.nsimplify(sympy.simplify(v), rational=True))
                    for k, v in sol.items()
                )
            )
        return out

    try:
        if normalise(sol_a) == normalise(sol_b):
            return Judgement(Outcome.EQUIVALENT, "solve", "mismo conjunto solución")
    except Exception as exc:  # noqa: BLE001
        return Judgement(Outcome.INCONCLUSIVE, "solve", f"no se pudieron comparar: {exc}")

    return Judgement(Outcome.DIFFERENT, "solve", "distinto conjunto solución")
