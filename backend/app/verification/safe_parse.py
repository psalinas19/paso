"""Parsing the `sympy` field without handing the model an eval().

`sympify()` evaluates arbitrary Python. The text in Step.sympy is produced by a
language model -- from recognition today, and from the model's own solutions in
SPEC 6.4 -- so it is untrusted input and never reaches eval unguarded.

Two layers, and the first one is load-bearing:

  1. An AST walk that rejects anything outside a small expression grammar.
     This is the primary defence, not a nicety. parse_expr evaluates attribute
     access, so `().__class__` alone returns the real `tuple` type even with a
     locked-down namespace -- the entry point to the usual __subclasses__()
     escape. Rejecting ast.Attribute is what stops it.
  2. parse_expr with an explicit local_dict and a global_dict whose
     `__builtins__` is empty, so a name like __import__ degrades to a harmless
     undefined function rather than resolving.

Both layers are pinned by tests in tests/test_safe_parse.py.
See docs/decisions/0002-sympy-dialect.md.
"""

from __future__ import annotations

import ast
from typing import Any

import sympy
from sympy.parsing.sympy_parser import (
    convert_xor,
    parse_expr,
    standard_transformations,
)

from app.subjects.loader import SubjectConfig

TRANSFORMATIONS = (*standard_transformations, convert_xor)

#: Callables and constants a step may reference. Anything else becomes a plain
#: Symbol (harmless) or, if called, an undefined Function (also harmless).
BASE_WHITELIST: dict[str, Any] = {
    # Relations and unevaluated operators
    "Eq": sympy.Eq,
    "Derivative": sympy.Derivative,
    "Integral": sympy.Integral,
    "diff": sympy.diff,
    "Sum": sympy.Sum,
    "Matrix": sympy.Matrix,
    # Numbers
    "Rational": sympy.Rational,
    "Integer": sympy.Integer,
    "Float": sympy.Float,
    # Elementary functions
    "sqrt": sympy.sqrt,
    "exp": sympy.exp,
    "log": sympy.log,
    "ln": sympy.log,
    "sin": sympy.sin,
    "cos": sympy.cos,
    "tan": sympy.tan,
    "cot": sympy.cot,
    "sec": sympy.sec,
    "csc": sympy.csc,
    "asin": sympy.asin,
    "acos": sympy.acos,
    "atan": sympy.atan,
    "atan2": sympy.atan2,
    "sinh": sympy.sinh,
    "cosh": sympy.cosh,
    "tanh": sympy.tanh,
    "Abs": sympy.Abs,
    "sign": sympy.sign,
    "factorial": sympy.factorial,
    "Piecewise": sympy.Piecewise,
    "Min": sympy.Min,
    "Max": sympy.Max,
    "re": sympy.re,
    "im": sympy.im,
    "conjugate": sympy.conjugate,
    # Constants
    "pi": sympy.pi,
    "E": sympy.E,
    "oo": sympy.oo,
    "zoo": sympy.zoo,
    "nan": sympy.nan,
}

# `integrate` is deliberately absent: it evaluates, which would turn a written
# "integrate both sides" step into its own antiderivative and hide an error in
# the next step. Integrals stay unevaluated as `Integral` until a strategy
# decides to evaluate them.

#: The globals the generated code runs under. The transformations rewrite bare
#: names into Symbol(...)/Function(...) calls, so those constructors have to be
#: in scope -- an empty global_dict does not work.
#:
#: `__builtins__` must be set explicitly: eval() injects the real builtins into
#: any globals mapping that lacks the key, so omitting it would hand the parsed
#: code open(), __import__ and friends.
PARSER_GLOBALS: dict[str, Any] = {
    "__builtins__": {},
    "Symbol": sympy.Symbol,
    "Function": sympy.Function,
    "Integer": sympy.Integer,
    "Float": sympy.Float,
    "Rational": sympy.Rational,
    "factorial": sympy.factorial,
}

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Call,
    ast.BinOp,
    ast.UnaryOp,
    ast.List,
    ast.Tuple,
    ast.keyword,
    # operators
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.BitXor,  # '^', rewritten to Pow by convert_xor
    ast.USub,
    ast.UAdd,
)


class UnsafeExpressionError(ValueError):
    """The text is outside the dialect's grammar. Always leads to
    `unverifiable`, never to `error`: failing to parse is our failure, not the
    student's."""


def _reject(reason: str) -> None:
    raise UnsafeExpressionError(reason)


def _guard_ast(text: str, forbidden_names: frozenset[str]) -> None:
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        _reject(f"no es una expresión válida: {exc.msg}")

    for node in ast.walk(tree):
        # Caught before the generic rejection so the message is actionable:
        # `x == 1` is a plausible thing for the model to emit.
        if isinstance(node, ast.Compare):
            _reject("usa Eq(lhs, rhs) en vez de '==' para una ecuación")

        if not isinstance(node, _ALLOWED_NODES):
            _reject(f"construcción no permitida: {type(node).__name__}")

        # bool is a subclass of int, so it has to be excluded on its own.
        if isinstance(node, ast.Constant) and (
            isinstance(node.value, bool) or not isinstance(node.value, int | float)
        ):
            _reject(f"literal no permitido: {node.value!r}")

        if isinstance(node, ast.Name):
            if node.id.startswith("_"):
                _reject(f"nombre no permitido: {node.id}")
            if node.id in forbidden_names:
                _reject(
                    f"'{node.id}' está reservado en esta materia; usa un subíndice, por ejemplo I_1"
                )

        # Only `name(...)` calls. Attribute access never reaches here because
        # ast.Attribute is not in the allowlist, which also blocks the
        # `().__class__.__bases__` style of escape.
        if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
            _reject("solo se permiten llamadas a funciones por nombre")


def build_local_dict(subject: SubjectConfig) -> dict[str, Any]:
    """Namespace for parsing, derived from the subject (ADR 0002).

    In a complex-domain subject 'j' is the imaginary unit; in a real-domain one
    it is an ordinary symbol, so I_1 and i_L stay currents.
    """
    local: dict[str, Any] = dict(BASE_WHITELIST)

    if subject.complex_domain:
        local["j"] = sympy.I
        local["I"] = sympy.I
    else:
        local.pop("re", None)
        local.pop("im", None)
        local.pop("conjugate", None)

    for name in subject.extra_functions:
        if hasattr(sympy, name):
            local[name] = getattr(sympy, name)

    return local


def safe_parse(text: str, subject: SubjectConfig) -> Any:
    """Parse one `sympy` field. Raises UnsafeExpressionError on anything odd."""
    if not text or not text.strip():
        _reject("expresión vacía")

    _guard_ast(text, subject.forbidden_symbols)

    try:
        parsed = parse_expr(
            text,
            local_dict=build_local_dict(subject),
            global_dict=dict(PARSER_GLOBALS),
            transformations=TRANSFORMATIONS,
            evaluate=True,
        )
    except UnsafeExpressionError:
        raise
    except Exception as exc:  # noqa: BLE001 - any parser failure is unverifiable
        _reject(f"SymPy no pudo interpretarla: {exc}")

    if isinstance(parsed, bool):
        # `x == 1` evaluates to a Python bool and silently loses the equation.
        _reject("usa Eq(lhs, rhs) en vez de '==' para una ecuación")

    if isinstance(parsed, list | tuple):
        return [_require_sympy(item) for item in parsed]

    return _require_sympy(parsed)


def _require_sympy(obj: Any) -> Any:
    if not isinstance(obj, sympy.Basic):
        _reject(f"el resultado no es una expresión de SymPy: {type(obj).__name__}")
    return obj


def try_parse(text: str | None, subject: SubjectConfig) -> tuple[Any | None, str | None]:
    """Non-raising variant. Returns (parsed, None) or (None, reason)."""
    if text is None:
        return None, "el paso no trae expresión simbólica"
    try:
        return safe_parse(text, subject), None
    except UnsafeExpressionError as exc:
        return None, str(exc)
