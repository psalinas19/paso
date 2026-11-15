"""Turn a handwritten equation into something the notebook can plot (SPEC 6.10).

The graph is computed from the step's `sympy` field, never from anything the
model says the curve looks like. Here the parsed expression becomes a small
tree of whitelisted operations; the notebook evaluates that tree itself, so
zooming and scrolling need no connection and a saved graph opens offline.

If the expression is not a function of one variable, or uses something the
tree cannot express, the answer is "no" with the reason. Drawing a curve that
is not the one on the page would be worse than drawing none.
"""

from __future__ import annotations

from typing import Any

import sympy
from sympy.core.function import AppliedUndef

from app.schemas import Step
from app.subjects.loader import SubjectConfig
from app.verification.safe_parse import try_parse

#: SymPy functions the notebook knows how to evaluate, by the name it uses.
FUNCTIONS: dict[Any, str] = {
    sympy.sin: "sin",
    sympy.cos: "cos",
    sympy.tan: "tan",
    sympy.asin: "asin",
    sympy.acos: "acos",
    sympy.atan: "atan",
    sympy.sinh: "sinh",
    sympy.cosh: "cosh",
    sympy.tanh: "tanh",
    sympy.exp: "exp",
    sympy.log: "log",
    sympy.Abs: "abs",
    sympy.sign: "sign",
    sympy.Heaviside: "heaviside",
}
MAX_NODES = 300


class NotPlottableError(ValueError):
    """The step cannot be drawn as y = f(x). The message says why, in Spanish."""


def to_tree(expr: Any, variable: sympy.Symbol, budget: list[int] | None = None) -> dict[str, Any]:
    """`expr` as nested {"n"|"v"|"op"|"f"} nodes. Raises on anything not whitelisted."""
    budget = budget if budget is not None else [MAX_NODES]
    budget[0] -= 1
    if budget[0] < 0:
        raise NotPlottableError("la expresión es demasiado larga para graficarla")

    def children() -> list[dict[str, Any]]:
        return [to_tree(arg, variable, budget) for arg in expr.args]

    if expr == variable:
        return {"v": 1}
    if isinstance(expr, sympy.Symbol):
        raise NotPlottableError(f"no sé cuánto vale «{expr}»")
    if expr.is_number:
        if expr.is_real is False or expr.has(sympy.I):
            raise NotPlottableError("tiene números complejos")
        value = float(expr)
        if value != value or value in (float("inf"), float("-inf")):
            raise NotPlottableError("tiene un valor que no es un número")
        return {"n": value}
    if isinstance(expr, sympy.Add):
        return {"op": "+", "args": children()}
    if isinstance(expr, sympy.Mul):
        return {"op": "*", "args": children()}
    if isinstance(expr, sympy.Pow):
        return {"op": "^", "args": children()}
    name = FUNCTIONS.get(expr.func)
    if name is not None and len(expr.args) == 1:
        return {"f": name, "args": children()}
    raise NotPlottableError(f"contiene «{type(expr).__name__}», que no sé graficar")


def _curve(parsed: Any, subject: SubjectConfig) -> tuple[Any, str]:
    """The expression to draw and the LaTeX name of what it gives (the "y")."""
    if isinstance(parsed, list | tuple):
        raise NotPlottableError("es un sistema de ecuaciones, no una sola función")
    name = "y"
    expr = parsed
    if isinstance(parsed, sympy.Equality):
        lone = [
            side
            for side in (parsed.lhs, parsed.rhs)
            if isinstance(side, sympy.Symbol | AppliedUndef)
        ]
        left_alone = bool(lone) and lone[0] is parsed.lhs
        other = parsed.rhs if left_alone else parsed.lhs
        dependent = lone[0] if lone else None
        symbol = dependent if isinstance(dependent, sympy.Symbol) else None
        if dependent is None or (symbol is not None and symbol in other.free_symbols):
            # x**2 + y**2 = 1, or y on both sides: solving for y is not ours to guess.
            raise NotPlottableError("no está despejada como y = f(x)")
        if isinstance(dependent, AppliedUndef) and other.has(type(dependent)):
            raise NotPlottableError("no está despejada como y = f(x)")
        if not other.free_symbols and str(dependent) in subject.independent_vars:
            # "x = 4" is where a development ends, not a curve: drawn as y = 4 it
            # would be a different statement from the one on the page.
            raise NotPlottableError(f"es el valor de {dependent}, no una función")
        name, expr = sympy.latex(dependent), other
    elif isinstance(parsed, sympy.core.relational.Relational):
        raise NotPlottableError("es una desigualdad, no una función")
    if expr.has(sympy.Derivative):
        expr = expr.doit()  # d/dx of something explicit is explicit; integrals are left alone
    return expr, name


def plot_of(subject: SubjectConfig, steps: list[Step]) -> dict[str, Any]:
    """The first step that can be drawn, as plain data for the notebook.

    Returns {"plottable": True, latex, label, variable, tree} or
    {"plottable": False, reason}: the reason is the first step's, since that
    is the equation the student meant.
    """
    reasons: list[str] = []
    for step in steps:
        if not step.is_symbolic:
            continue
        parsed, problem = try_parse(step.sympy, subject)
        if parsed is None:
            reasons.append(f"no pude interpretar lo que se leyó ({problem})")
            continue
        try:
            expr, label = _curve(parsed, subject)
            free = sorted(expr.free_symbols, key=str)
            if len(free) > 1:
                names = ", ".join(str(s) for s in free)
                raise NotPlottableError(
                    f"tiene más de una variable ({names}): dale un valor a las demás"
                )
            variable = free[0] if free else sympy.Symbol(subject.independent_vars[0])
            tree = to_tree(expr, variable)
        except NotPlottableError as exc:
            reasons.append(str(exc))
            continue
        return {
            "plottable": True,
            "latex": step.latex,
            "label": label,
            "variable": str(variable),
            "tree": tree,
        }
    reason = reasons[0] if reasons else "no encontré una ecuación legible en la selección"
    return {"plottable": False, "reason": reason}


def plot_in_process(
    subject_data: dict[str, Any], steps_data: list[dict[str, Any]]
) -> dict[str, Any]:
    """Entry point for the timeout worker: only JSON-able values cross the boundary."""
    subject = SubjectConfig.model_validate(subject_data)
    return plot_of(subject, [Step.model_validate(s) for s in steps_data])
