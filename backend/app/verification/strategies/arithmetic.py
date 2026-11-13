"""Plain arithmetic: an equality with no unknowns is true or false on its own.

`5 + 5 = 12` needs no previous step to be checked, so this runs before the
relation is even looked at. Without it such a line, read as a `given`, came back
"correct: nothing to check" -- found on the first real review from the iPad.
"""

from __future__ import annotations

import ast
import re
from typing import Any

import sympy

from app.schemas import Step, StepKind, StepVerification
from app.verification.registry import VerifyContext, register
from app.verification.safe_parse import try_parse
from app.verification.strategies.base import correct, wrong

_DECIMALS = re.compile(r"\d\.(\d+)")


def closed_claims(step: Step, ctx: VerifyContext) -> list[tuple[Any, Any]] | None:
    """The (left, right) values of each equality in the step, if every one of them
    is a pure number. None as soon as anything is not: an unknown, a function, an
    infinity, a side that does not parse.

    The sides are parsed separately because SymPy collapses `Eq(5 + 5, 12)` to a
    bare False, which says the claim is wrong but not what each side is worth.
    """
    if not step.is_symbolic:
        return None
    try:
        tree = ast.parse((step.sympy or "").replace("^", "**"), mode="eval").body
    except SyntaxError:
        return None

    claims: list[tuple[Any, Any]] = []
    for node in tree.elts if isinstance(tree, ast.List | ast.Tuple) else [tree]:
        is_eq = isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        if not is_eq or node.func.id != "Eq" or len(node.args) != 2 or node.keywords:
            return None
        sides = []
        for arg in node.args:
            value, _ = try_parse(ast.unparse(arg), ctx.subject)
            if not isinstance(value, sympy.Basic) or value.free_symbols:
                return None
            number = sympy.N(value.doit())  # doit: a definite integral is a number too
            if not (number.is_number and number.is_real and number.is_finite):
                return None
            sides.append(number)
        claims.append((sides[0], sides[1]))
    return claims or None


def _tolerance(step: Step, ctx: VerifyContext, scale: float) -> float:
    """Exact when only whole numbers and fractions were written. When decimals were,
    forgive rounding or truncating at the last written digit, plus the subject's
    hand-rounding allowance: `1/3 = 0.33` is not a mistake (a false cross is the
    worst failure there is, ADR 0004)."""
    tolerance = ctx.subject.tolerance
    written = [len(m) for m in _DECIMALS.findall(step.sympy or "")]
    if not written:
        return tolerance.absolute
    return max(tolerance.absolute, 1.5 * 10 ** -max(written), tolerance.hand_rounding * scale)


def _show(value: Any) -> str:
    number = float(value)
    return str(int(number)) if number == int(number) else f"{number:.6g}"


class ArithmeticStrategy:
    name = "arithmetic"
    # Ahead of `given` (10): a false sum is false even when written as a premise.
    priority = 5
    kinds = frozenset(StepKind)
    always_enabled = True

    def applies(self, step: Step, ctx: VerifyContext) -> bool:
        return closed_claims(step, ctx) is not None

    def verify(self, step: Step, ctx: VerifyContext) -> StepVerification:
        for left, right in closed_claims(step, ctx) or []:
            scale = max(abs(float(left)), abs(float(right)))
            if abs(float(left - right)) > _tolerance(step, ctx, scale):
                return wrong(
                    step,
                    self.name,
                    f"La cuenta no da: el lado izquierdo vale {_show(left)} "
                    f"y el derecho {_show(right)}.",
                )
        return correct(step, self.name, "La cuenta es correcta.")


register(ArithmeticStrategy())
