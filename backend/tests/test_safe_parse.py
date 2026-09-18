"""The parser is the trust boundary: everything here is untrusted model output."""

from __future__ import annotations

import pytest
import sympy

from app.subjects.loader import SubjectConfig
from app.verification.safe_parse import (
    TRANSFORMATIONS,
    UnsafeExpressionError,
    safe_parse,
    try_parse,
)


@pytest.fixture
def real_subject() -> SubjectConfig:
    return SubjectConfig(slug="test", name="Test", complex_domain=False)


@pytest.fixture
def complex_subject() -> SubjectConfig:
    return SubjectConfig(slug="test_ac", name="Test AC", complex_domain=True)


# --- the dialect of ADR 0002 parses as specified ---------------------------


def test_applied_function_stays_a_function(real_subject):
    """y(x) must be an applied undefined function, not y*x -- checkodesol needs it."""
    parsed = safe_parse("y(x)", real_subject)
    assert isinstance(parsed, sympy.core.function.AppliedUndef)
    assert parsed.func.__name__ == "y"


def test_unevaluated_derivative(real_subject):
    parsed = safe_parse("Derivative(y(x), x)", real_subject)
    assert isinstance(parsed, sympy.Derivative)


def test_second_derivative(real_subject):
    parsed = safe_parse("Derivative(y(x), x, 2)", real_subject)
    assert parsed.derivative_count == 2


def test_integral_is_not_evaluated(real_subject):
    """An 'integrate both sides' step must stay unevaluated, or it would already
    contain the answer and mask an error in the next step."""
    parsed = safe_parse("Integral(x**2, x)", real_subject)
    assert isinstance(parsed, sympy.Integral)


def test_equation(real_subject):
    parsed = safe_parse("Eq(y(x), C1*exp(x))", real_subject)
    assert isinstance(parsed, sympy.Eq)


def test_system_is_a_list_of_equations(real_subject):
    parsed = safe_parse("[Eq(V_1, 10), Eq(V_2, 5)]", real_subject)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert all(isinstance(e, sympy.Eq) for e in parsed)


def test_caret_is_a_power(real_subject):
    assert safe_parse("x^2", real_subject) == safe_parse("x**2", real_subject)


def test_fraction_is_exact(real_subject):
    parsed = safe_parse("1/2", real_subject)
    assert parsed == sympy.Rational(1, 2)


def test_subscripted_symbols_are_single_symbols(real_subject):
    parsed = safe_parse("R_eq + V_1", real_subject)
    assert {s.name for s in parsed.free_symbols} == {"R_eq", "V_1"}


def test_ln_is_log(real_subject):
    assert safe_parse("ln(x)", real_subject) == safe_parse("log(x)", real_subject)


# --- the imaginary-unit collision (R3) -------------------------------------


def test_real_subject_treats_I_as_an_ordinary_current(real_subject):
    """In DC circuits I_1 and I are currents, not the imaginary unit."""
    parsed = safe_parse("I_1 + I_2", real_subject)
    assert all(s.is_Symbol for s in parsed.free_symbols)
    assert sympy.I not in parsed.atoms()


def test_complex_subject_maps_j_to_the_imaginary_unit(complex_subject):
    assert safe_parse("j", complex_subject) == sympy.I
    assert safe_parse("2 + 3*j", complex_subject) == 2 + 3 * sympy.I


def test_complex_subject_forbids_bare_I(complex_subject):
    with pytest.raises(UnsafeExpressionError, match="reservado"):
        safe_parse("I + 1", complex_subject)


def test_complex_subject_still_allows_subscripted_currents(complex_subject):
    parsed = safe_parse("I_1 + I_x", complex_subject)
    assert {s.name for s in parsed.free_symbols} == {"I_1", "I_x"}


# --- hostile input ----------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "__import__('os').system('echo pwned')",
        "().__class__.__bases__",
        "x.__class__",
        "(lambda: 1)()",
        "[i for i in range(3)]",
        "open('secrets.txt')",
        "exec('x=1')",
        "{'a': 1}",
        "x if True else y",
        "*args",
        "x := 1",
        "f'{x}'",
        "'a string'",
    ],
)
def test_hostile_payloads_are_rejected(payload, real_subject):
    with pytest.raises(UnsafeExpressionError):
        safe_parse(payload, real_subject)


def test_attribute_access_is_rejected(real_subject):
    with pytest.raises(UnsafeExpressionError, match="no permitida|válida"):
        safe_parse("sympy.Symbol", real_subject)


def test_double_equals_is_rejected_rather_than_silently_false(real_subject):
    """`x == 1` evaluates to a bool and would lose the equation entirely."""
    with pytest.raises(UnsafeExpressionError, match="Eq"):
        safe_parse("x == 1", real_subject)


def test_integrate_is_not_available(real_subject):
    """`integrate` would evaluate; only the unevaluated `Integral` is allowed."""
    parsed = safe_parse("integrate(x, x)", real_subject)
    assert not isinstance(parsed, sympy.Integral)
    # It degrades to an undefined function, which no strategy will accept.
    assert isinstance(parsed, sympy.core.function.AppliedUndef)


def test_empty_is_rejected(real_subject):
    with pytest.raises(UnsafeExpressionError):
        safe_parse("   ", real_subject)


def _raw_parse(text: str, subject: SubjectConfig):
    """parse_expr with our namespaces but WITHOUT the AST guard -- layer 2 alone."""
    from sympy.parsing.sympy_parser import parse_expr as raw_parse_expr

    from app.verification.safe_parse import PARSER_GLOBALS, build_local_dict

    return raw_parse_expr(
        text,
        local_dict=build_local_dict(subject),
        global_dict=dict(PARSER_GLOBALS),
        transformations=TRANSFORMATIONS,
    )


def test_builtins_are_not_in_scope_for_the_parser(real_subject):
    """Layer 2: the eval parse_expr performs must not see builtins, so a call to
    __import__ degrades to a harmless undefined function instead of importing."""
    from app.verification.safe_parse import PARSER_GLOBALS

    assert PARSER_GLOBALS["__builtins__"] == {}

    result = _raw_parse("__import__('os')", real_subject)
    assert isinstance(result, sympy.core.function.AppliedUndef)


def test_ast_guard_is_load_bearing_for_attribute_access(real_subject):
    """Do not remove the AST guard believing a restricted global_dict is enough.

    It is not: parse_expr happily evaluates attribute access, and `().__class__`
    comes back as the real `tuple` type -- the entry point to the usual
    __subclasses__() escape. Rejecting ast.Attribute is what actually stops it.
    """
    escaped = _raw_parse("().__class__", real_subject)
    assert escaped is tuple, "premise of this test changed; re-audit safe_parse"

    with pytest.raises(UnsafeExpressionError):
        safe_parse("().__class__", real_subject)


# --- the non-raising wrapper -----------------------------------------------


def test_try_parse_reports_reason_instead_of_raising(real_subject):
    parsed, reason = try_parse("__import__('os')", real_subject)
    assert parsed is None
    assert reason


def test_try_parse_handles_none(real_subject):
    parsed, reason = try_parse(None, real_subject)
    assert parsed is None
    assert "simbólica" in reason
