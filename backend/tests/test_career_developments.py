"""Developments of the kind the degree is made of, checked end to end.

Each one is written the way the model plausibly transcribes it, sloppy relation
labels included, because that is what reaches the verifier in real use.

Two promises are pinned here:

- CORRECT: none of these may produce an `error`. The first real session on the
  iPad marked a correct second-order ODE as wrong; twelve of these cases did the
  same before the verifier learned to tell "different" from "not comparable".
- WRONG: the one real mistake in each is still caught, and nothing else is
  blamed for it. Being careful must not turn into being blind.
"""

from __future__ import annotations

import pytest

from app.schemas import StepKind as K
from app.schemas import StepRelation as R
from app.schemas import VerificationStatus as S
from app.subjects.loader import load_subject
from tests.conftest import mkstep, run


def st(step_id, sympy_text, kind, relation, parents=()):
    return mkstep(step_id, sympy_text, kind, relation, tuple(parents))


Y2 = "Derivative(y(x), x, 2)"
Y1 = "Derivative(y(x), x)"
CORRECT = {
    "ED2 homogenea, raices reales (relaciones bien)": (
        "ed",
        [
            st("s1", f"Eq({Y2} + 3*{Y1} + 2*y(x), 0)", K.ODE, R.GIVEN),
            st("s2", "Eq(r**2 + 3*r + 2, 0)", K.EQUATION, R.ASSERTION),
            st("s3", "Eq((r + 1)*(r + 2), 0)", K.EQUATION, R.EQUIVALENT, ["s2"]),
            st("s4", "[Eq(r_1, -1), Eq(r_2, -2)]", K.SYSTEM, R.EQUIVALENT, ["s3"]),
            st("s5", "Eq(y(x), C1*exp(-x) + C2*exp(-2*x))", K.ODE, R.RESULT, ["s4"]),
        ],
    ),
    "ED2 homogenea, etiquetas descuidadas": (
        "ed",
        [
            st("s1", f"Eq({Y2} + 3*{Y1} + 2*y(x), 0)", K.ODE, R.GIVEN),
            st("s2", "Eq(r**2 + 3*r + 2, 0)", K.EQUATION, R.EQUIVALENT, ["s1"]),
            st("s3", "Eq((r + 1)*(r + 2), 0)", K.EQUATION, R.EQUIVALENT, ["s2"]),
            st("s4", "Eq(r_1, -1)", K.EQUATION, R.EQUIVALENT, ["s3"]),
            st("s5", "Eq(r_2, -2)", K.EQUATION, R.EQUIVALENT, ["s3"]),
            st("s6", "Eq(y(x), C1*exp(-x) + C2*exp(-2*x))", K.EQUATION, R.EQUIVALENT, ["s5"]),
        ],
    ),
    "ED2 raices con formula general": (
        "ed",
        [
            st("s1", f"Eq({Y2} + 2*{Y1} + 5*y(x), 0)", K.ODE, R.GIVEN),
            st("s2", "Eq(m**2 + 2*m + 5, 0)", K.EQUATION, R.SUBSTITUTION, ["s1"]),
            st("s3", "Eq(m, (-2 + sqrt(4 - 20))/2)", K.EQUATION, R.EQUIVALENT, ["s2"]),
            st("s4", "Eq(m, -1 + 2*I)", K.EQUATION, R.EQUIVALENT, ["s3"]),
            st("s5", "Eq(y(x), exp(-x)*(C1*cos(2*x) + C2*sin(2*x)))", K.ODE, R.RESULT, ["s4"]),
        ],
    ),
    "ED2 raiz doble": (
        "ed",
        [
            st("s1", f"Eq({Y2} - 4*{Y1} + 4*y(x), 0)", K.ODE, R.GIVEN),
            st("s2", "Eq(r**2 - 4*r + 4, 0)", K.EQUATION, R.ASSERTION),
            st("s3", "Eq((r - 2)**2, 0)", K.EQUATION, R.EQUIVALENT, ["s2"]),
            st("s4", "Eq(r, 2)", K.EQUATION, R.EQUIVALENT, ["s3"]),
            st("s5", "Eq(y(x), C1*exp(2*x) + C2*x*exp(2*x))", K.ODE, R.RESULT, ["s4"]),
        ],
    ),
    "ED2 no homogenea, coeficientes indeterminados": (
        "ed",
        [
            st("s1", f"Eq({Y2} - y(x), exp(2*x))", K.ODE, R.GIVEN),
            st("s2", "Eq(r**2 - 1, 0)", K.EQUATION, R.EQUIVALENT, ["s1"]),
            st("s3", "Eq(y_h, C1*exp(x) + C2*exp(-x))", K.EQUATION, R.EQUIVALENT, ["s2"]),
            st("s4", "Eq(y_p, A*exp(2*x))", K.EQUATION, R.ASSERTION),
            st(
                "s5",
                "Eq(4*A*exp(2*x) - A*exp(2*x), exp(2*x))",
                K.EQUATION,
                R.SUBSTITUTION,
                ["s4", "s1"],
            ),
            st("s6", "Eq(3*A, 1)", K.EQUATION, R.EQUIVALENT, ["s5"]),
            st("s7", "Eq(A, 1/3)", K.EQUATION, R.EQUIVALENT, ["s6"]),
            st(
                "s8", "Eq(y(x), C1*exp(x) + C2*exp(-x) + exp(2*x)/3)", K.ODE, R.RESULT, ["s3", "s7"]
            ),
        ],
    ),
    "PVI de segundo orden": (
        "ed",
        [
            st("s1", f"Eq({Y2} + y(x), 0)", K.ODE, R.GIVEN),
            st("s2", "Eq(y(0), 1)", K.EQUATION, R.GIVEN),
            st("s3", "Eq(y(x), C1*cos(x) + C2*sin(x))", K.ODE, R.EQUIVALENT, ["s1"]),
            st("s4", "Eq(C1, 1)", K.EQUATION, R.SPECIALIZATION, ["s3"]),
            st("s5", f"Eq({Y1}, -C1*sin(x) + C2*cos(x))", K.ODE, R.EQUIVALENT, ["s3"]),
            st("s6", "Eq(C2, 0)", K.EQUATION, R.SPECIALIZATION, ["s5"]),
            st("s7", "Eq(y(x), cos(x))", K.ODE, R.RESULT, ["s3", "s4", "s6"]),
        ],
    ),
    "Lineal 1er orden, factor integrante": (
        "ed",
        [
            st("s1", f"Eq({Y1} + 2*y(x), exp(-x))", K.ODE, R.GIVEN),
            st("s2", "Eq(mu, exp(2*x))", K.EQUATION, R.EQUIVALENT, ["s1"]),
            st("s3", "Eq(Derivative(exp(2*x)*y(x), x), exp(x))", K.ODE, R.EQUIVALENT, ["s1"]),
            st("s4", "Eq(exp(2*x)*y(x), exp(x) + C1)", K.EQUATION, R.EQUIVALENT, ["s3"]),
            st("s5", "Eq(y(x), exp(-x) + C1*exp(-2*x))", K.ODE, R.RESULT, ["s4"]),
        ],
    ),
    "Separable": (
        "ed",
        [
            st("s1", f"Eq({Y1}, 2*x*y(x))", K.ODE, R.GIVEN),
            st("s2", "Eq(Integral(1/y, y), Integral(2*x, x))", K.EQUATION, R.EQUIVALENT, ["s1"]),
            st("s3", "Eq(log(Abs(y)), x**2 + C1)", K.EQUATION, R.EQUIVALENT, ["s2"]),
            st("s4", "Eq(y(x), C2*exp(x**2))", K.ODE, R.RESULT, ["s3"]),
        ],
    ),
    "Algebra: dividir entre un parametro": (
        "general",
        [
            st("s1", "Eq(m*a, F)", K.EQUATION, R.GIVEN),
            st("s2", "Eq(a, F/m)", K.EQUATION, R.EQUIVALENT, ["s1"]),
            st("s3", "Eq(a*x, 2*a)", K.EQUATION, R.ASSERTION),
            st("s4", "Eq(x, 2)", K.EQUATION, R.EQUIVALENT, ["s3"]),
        ],
    ),
    "Sustituir valores calculados antes (no dados)": (
        "general",
        [
            st("s1", "Eq(V, i*R)", K.EQUATION, R.ASSERTION),
            st("s2", "Eq(i, 2)", K.EQUATION, R.ASSERTION),
            st("s3", "Eq(R, 5)", K.EQUATION, R.ASSERTION),
            st("s4", "Eq(V, 10)", K.EQUATION, R.EQUIVALENT, ["s1"]),
            st("s5", "Eq(P, V*i)", K.EQUATION, R.ASSERTION),
            st("s6", "Eq(P, 20)", K.EQUATION, R.SUBSTITUTION, ["s5"]),
        ],
    ),
    "Cuadratica con dos soluciones": (
        "general",
        [
            st("s1", "Eq(x**2 - 5*x + 6, 0)", K.EQUATION, R.GIVEN),
            st("s2", "Eq((x - 2)*(x - 3), 0)", K.EQUATION, R.EQUIVALENT, ["s1"]),
            st("s3", "[Eq(x_1, 2), Eq(x_2, 3)]", K.SYSTEM, R.RESULT, ["s2"]),
        ],
    ),
    "Cuadratica, una raiz por paso": (
        "general",
        [
            st("s1", "Eq(x**2 - 5*x + 6, 0)", K.EQUATION, R.GIVEN),
            st("s2", "Eq(x, 2)", K.EQUATION, R.EQUIVALENT, ["s1"]),
            st("s3", "Eq(x, 3)", K.EQUATION, R.EQUIVALENT, ["s1"]),
        ],
    ),
    "Sistema 2x2 por sustitucion": (
        "general",
        [
            st("s1", "[Eq(x + y, 5), Eq(x - y, 1)]", K.SYSTEM, R.GIVEN),
            st("s2", "Eq(2*x, 6)", K.EQUATION, R.EQUIVALENT, ["s1"]),
            st("s3", "Eq(x, 3)", K.EQUATION, R.EQUIVALENT, ["s2"]),
            st("s4", "Eq(3 + y, 5)", K.EQUATION, R.SUBSTITUTION, ["s1", "s3"]),
            st("s5", "Eq(y, 2)", K.EQUATION, R.EQUIVALENT, ["s4"]),
        ],
    ),
    "Derivada con regla de la cadena": (
        "general",
        [
            st("s1", "Eq(f(x), sin(x**2))", K.EQUATION, R.GIVEN),
            st("s2", "Eq(Derivative(f(x), x), cos(x**2)*2*x)", K.EQUATION, R.EQUIVALENT, ["s1"]),
        ],
    ),
    "Integral por partes": (
        "general",
        [
            st("s1", "Integral(x*exp(x), x)", K.EXPRESSION, R.GIVEN),
            st("s2", "x*exp(x) - Integral(exp(x), x)", K.EXPRESSION, R.EQUIVALENT, ["s1"]),
            st("s3", "x*exp(x) - exp(x) + C1", K.EXPRESSION, R.EQUIVALENT, ["s2"]),
        ],
    ),
    "Integral definida": (
        "general",
        [
            st("s1", "Integral(3*x**2, (x, 0, 2))", K.EXPRESSION, R.GIVEN),
            st("s2", "Eq(Integral(3*x**2, (x, 0, 2)), 8)", K.EQUATION, R.EQUIVALENT, ["s1"]),
        ],
    ),
    "Divisor de voltaje con numeros": (
        "circuitos1",
        [
            st("s1", "Eq(V_s, 12)", K.EQUATION, R.GIVEN),
            st("s2", "Eq(R_1, 1000)", K.EQUATION, R.GIVEN),
            st("s3", "Eq(R_2, 2000)", K.EQUATION, R.GIVEN),
            st("s4", "Eq(V_2, V_s*R_2/(R_1 + R_2))", K.EQUATION, R.ASSERTION),
            st("s5", "Eq(V_2, 12*2000/(1000 + 2000))", K.EQUATION, R.SUBSTITUTION, ["s4"]),
            st("s6", "Eq(V_2, 8)", K.EQUATION, R.EQUIVALENT, ["s5"]),
        ],
    ),
    "Nodal 2 nodos": (
        "circuitos1",
        [
            st("s1", "Eq((V_1 - 10)/2 + V_1/4 + (V_1 - V_2)/2, 0)", K.EQUATION, R.ASSERTION),
            st("s2", "Eq((V_2 - V_1)/2 + V_2/6, 0)", K.EQUATION, R.ASSERTION),
            st(
                "s3",
                "[Eq(5*V_1 - 2*V_2, 20), Eq(-3*V_1 + 4*V_2, 0)]",
                K.SYSTEM,
                R.EQUIVALENT,
                ["s1", "s2"],
            ),
            st("s4", "[Eq(V_1, 40/7), Eq(V_2, 30/7)]", K.SYSTEM, R.RESULT, ["s3"]),
        ],
    ),
    "Funcion de transferencia": (
        "general",
        [
            st("s1", "Eq(G(s), 1/(s + 2))", K.EQUATION, R.GIVEN),
            st("s2", "Eq(H(s), 1)", K.EQUATION, R.GIVEN),
            st("s3", "Eq(T(s), G(s)/(1 + G(s)*H(s)))", K.EQUATION, R.ASSERTION),
            st("s4", "Eq(T(s), (1/(s + 2))/(1 + 1/(s + 2)))", K.EQUATION, R.SUBSTITUTION, ["s3"]),
            st("s5", "Eq(T(s), 1/(s + 3))", K.EQUATION, R.EQUIVALENT, ["s4"]),
        ],
    ),
    "Newton-Raphson": (
        "general",
        [
            st("s1", "Eq(f(x), x**2 - 2)", K.EQUATION, R.GIVEN),
            st("s2", "Eq(x_0, 1)", K.EQUATION, R.GIVEN),
            st(
                "s3",
                "Eq(x_1, 1 - (1 - 2)/(2*1))",
                K.NUMERIC_ITERATION,
                R.SUBSTITUTION,
                ["s1", "s2"],
            ),
            st("s4", "Eq(x_1, 1.5)", K.EQUATION, R.EQUIVALENT, ["s3"]),
        ],
    ),
    "Laplace inversa directa (expresiones)": (
        "general",
        [
            st("s1", "InverseLaplaceTransform(3/(s**2 + 9), s, t)", K.EXPRESSION, R.GIVEN),
            st("s2", "sin(3*t)", K.EXPRESSION, R.EQUIVALENT, ["s1"]),
        ],
    ),
    "Laplace inversa como ecuacion (resultado)": (
        "general",
        [
            st("s1", "InverseLaplaceTransform(1/(s*(s + 1)), s, t)", K.EXPRESSION, R.GIVEN),
            st(
                "s2",
                "InverseLaplaceTransform(1/s - 1/(s + 1), s, t)",
                K.EXPRESSION,
                R.EQUIVALENT,
                ["s1"],
            ),
            st(
                "s3",
                "Eq(InverseLaplaceTransform(1/s - 1/(s + 1), s, t), 1 - exp(-t))",
                K.EQUATION,
                R.RESULT,
                ["s2"],
            ),
        ],
    ),
    "Laplace inversa con F(s) y f(t)": (
        "general",
        [
            st("s1", "Eq(F(s), (s + 3)/(s**2 + 2*s + 5))", K.EQUATION, R.GIVEN),
            st(
                "s2",
                "Eq(F(s), (s + 1)/((s + 1)**2 + 4) + 2/((s + 1)**2 + 4))",
                K.EQUATION,
                R.EQUIVALENT,
                ["s1"],
            ),
            st("s3", "Eq(f(t), exp(-t)*cos(2*t) + exp(-t)*sin(2*t))", K.EQUATION, R.RESULT, ["s2"]),
        ],
    ),
    "Laplace directa": (
        "general",
        [
            st("s1", "Eq(f(t), t*exp(-2*t))", K.EQUATION, R.GIVEN),
            st("s2", "Eq(F(s), 1/(s + 2)**2)", K.EQUATION, R.EQUIVALENT, ["s1"]),
            st("s3", "Eq(LaplaceTransform(sin(2*t), t, s), 2/(s**2 + 4))", K.EQUATION, R.ASSERTION),
        ],
    ),
    "EDO por Laplace": (
        "ed",
        [
            st("s1", "Eq(Derivative(y(t), t, 2) + y(t), 0)", K.ODE, R.GIVEN),
            st("s2", "Eq(y(0), 1)", K.EQUATION, R.GIVEN),
            st("s3", "Eq(s**2*Y(s) - s + Y(s), 0)", K.EQUATION, R.EQUIVALENT, ["s1"]),
            st("s4", "Eq(Y(s), s/(s**2 + 1))", K.EQUATION, R.EQUIVALENT, ["s3"]),
            st("s5", "Eq(y(t), cos(t))", K.ODE, R.RESULT, ["s4"]),
        ],
    ),
    "Fracciones parciales": (
        "general",
        [
            st("s1", "Eq(F(s), (2*s + 1)/((s + 1)*(s + 2)))", K.EQUATION, R.GIVEN),
            st(
                "s2",
                "Eq((2*s + 1)/((s + 1)*(s + 2)), A/(s + 1) + B/(s + 2))",
                K.EQUATION,
                R.ASSERTION,
            ),
            st("s3", "Eq(2*s + 1, A*(s + 2) + B*(s + 1))", K.EQUATION, R.EQUIVALENT, ["s2"]),
            st("s4", "Eq(A, -1)", K.EQUATION, R.EQUIVALENT, ["s3"]),
            st("s5", "Eq(B, 3)", K.EQUATION, R.EQUIVALENT, ["s3"]),
            st("s6", "Eq(F(s), -1/(s + 1) + 3/(s + 2))", K.EQUATION, R.EQUIVALENT, ["s1"]),
            st("s7", "Eq(f(t), -exp(-t) + 3*exp(-2*t))", K.EQUATION, R.RESULT, ["s6"]),
        ],
    ),
    "Respuesta al escalon (no es par de transformadas)": (
        "general",
        [
            st("s1", "Eq(G(s), 1/(s + 2))", K.EQUATION, R.GIVEN),
            st("s2", "Eq(y(t), (1 - exp(-2*t))/2)", K.EQUATION, R.RESULT, ["s1"]),
        ],
    ),
}

WRONG = {
    "ED2: signo en la solucion": (
        "ed",
        [
            st("s1", f"Eq({Y2} + 3*{Y1} + 2*y(x), 0)", K.ODE, R.GIVEN),
            st("s2", "Eq(r**2 + 3*r + 2, 0)", K.EQUATION, R.ASSERTION),
            st("s3", "Eq(y(x), C1*exp(x) + C2*exp(-2*x))", K.ODE, R.RESULT, ["s2"]),
        ],
        "s3",
    ),
    "ED2: raiz equivocada": (
        "ed",
        [
            st("s1", f"Eq({Y2} + 3*{Y1} + 2*y(x), 0)", K.ODE, R.GIVEN),
            st("s2", "Eq(r**2 + 3*r + 2, 0)", K.EQUATION, R.ASSERTION),
            st("s3", "[Eq(r_1, 1), Eq(r_2, -2)]", K.SYSTEM, R.EQUIVALENT, ["s2"]),
        ],
        "s3",
    ),
    "PVI: constante mal": (
        "ed",
        [
            st("s1", f"Eq({Y2} + y(x), 0)", K.ODE, R.GIVEN),
            st("s2", "Eq(y(0), 1)", K.EQUATION, R.GIVEN),
            st("s3", "Eq(y(x), C1*cos(x) + C2*sin(x))", K.ODE, R.EQUIVALENT, ["s1"]),
            st("s4", "Eq(C1, 2)", K.EQUATION, R.SPECIALIZATION, ["s3"]),
        ],
        "s4",
    ),
    "Regla de la cadena olvidada": (
        "general",
        [
            st("s1", "Eq(f(x), sin(x**2))", K.EQUATION, R.GIVEN),
            st("s2", "Eq(Derivative(f(x), x), cos(x**2))", K.EQUATION, R.EQUIVALENT, ["s1"]),
        ],
        "s2",
    ),
    "Falta la constante de integracion": (
        "general",
        [
            st("s1", "Integral(2*x, x)", K.EXPRESSION, R.GIVEN),
            st("s2", "x**2", K.EXPRESSION, R.EQUIVALENT, ["s1"]),
        ],
        "s2",
    ),
    "Signo al despejar": (
        "general",
        [
            st("s1", "Eq(3*x + 2, 9)", K.EQUATION, R.GIVEN),
            st("s2", "Eq(3*x, 11)", K.EQUATION, R.EQUIVALENT, ["s1"]),
        ],
        "s2",
    ),
    "Laplace inversa equivocada": (
        "general",
        [
            st("s1", "InverseLaplaceTransform(3/(s**2 + 9), s, t)", K.EXPRESSION, R.GIVEN),
            st("s2", "cos(3*t)", K.EXPRESSION, R.EQUIVALENT, ["s1"]),
        ],
        "s2",
    ),
    "Laplace inversa equivocada (par F, f)": (
        "general",
        [
            st("s1", "Eq(F(s), 1/(s + 2))", K.EQUATION, R.GIVEN),
            st("s2", "Eq(f(t), exp(2*t))", K.EQUATION, R.RESULT, ["s1"]),
        ],
        "s2",
    ),
    "Tabla de Laplace mal": (
        "general",
        [
            st("s1", "Eq(LaplaceTransform(sin(2*t), t, s), s/(s**2 + 4))", K.EQUATION, R.ASSERTION),
        ],
        "s1",
    ),
    "Fracciones parciales: coeficiente mal": (
        "general",
        [
            st("s1", "Eq(2*s + 1, A*(s + 2) + B*(s + 1))", K.EQUATION, R.ASSERTION),
            st("s2", "Eq(A, 1)", K.EQUATION, R.EQUIVALENT, ["s1"]),
        ],
        "s2",
    ),
    "Nodal: sistema mal resuelto": (
        "circuitos1",
        [
            st("s1", "[Eq(5*V_1 - 2*V_2, 20), Eq(-3*V_1 + 4*V_2, 0)]", K.SYSTEM, R.ASSERTION),
            st("s2", "[Eq(V_1, 4), Eq(V_2, 3)]", K.SYSTEM, R.RESULT, ["s1"]),
        ],
        "s2",
    ),
    "Sustitucion numerica mal": (
        "circuitos1",
        [
            st("s1", "Eq(V_s, 12)", K.EQUATION, R.GIVEN),
            st("s2", "Eq(R_1, 1000)", K.EQUATION, R.GIVEN),
            st("s3", "Eq(R_2, 2000)", K.EQUATION, R.GIVEN),
            st("s4", "Eq(V_2, V_s*R_2/(R_1 + R_2))", K.EQUATION, R.ASSERTION),
            st("s5", "Eq(V_2, 6)", K.EQUATION, R.SUBSTITUTION, ["s4"]),
        ],
        "s5",
    ),
    "Integral definida mal": (
        "general",
        [
            st("s1", "Eq(Integral(3*x**2, (x, 0, 2)), 6)", K.EQUATION, R.ASSERTION),
        ],
        "s1",
    ),
}


@pytest.mark.parametrize("name", CORRECT)
def test_correct_work_is_never_marked_wrong(name):
    subject, steps = CORRECT[name]
    result = run(load_subject(subject), steps)
    for step in steps:
        verdict = result.by_id()[step.id]
        assert verdict.status is not S.ERROR, (
            f"falso error en {step.id} ({step.sympy}): {verdict.method_used}: {verdict.detail}"
        )


@pytest.mark.parametrize("name", WRONG)
def test_the_real_mistake_is_still_caught_and_nothing_else_is_blamed(name):
    subject, steps, wrong_id = WRONG[name]
    result = run(load_subject(subject), steps)
    verdicts = result.by_id()
    assert verdicts[wrong_id].status is S.ERROR, (
        f"no se detectó: {verdicts[wrong_id].method_used}: {verdicts[wrong_id].detail}"
    )
    assert [s.id for s in steps if s.id != wrong_id and verdicts[s.id].status is S.ERROR] == []


def test_a_good_share_of_correct_steps_is_actually_proved():
    """Refusing to judge is safe but useless if it becomes the answer to everything."""
    proved = total = 0
    for subject, steps in CORRECT.values():
        result = run(load_subject(subject), steps)
        for step in steps:
            if step.relation is R.GIVEN:
                continue
            total += 1
            proved += result.by_id()[step.id].status is S.CORRECT
    assert proved / total > 0.6, f"solo {proved} de {total} pasos correctos se comprobaron"


def test_a_crash_inside_a_check_is_unverifiable_not_a_failed_review(monkeypatch):
    from app.verification.strategies.equation import EquationStrategy

    def explode(self, parent, current, subject):
        raise RuntimeError("boom")

    monkeypatch.setattr(EquationStrategy, "compare", explode)
    steps = [
        st("s1", "Eq(2*x + y, 10)", K.EQUATION, R.GIVEN),
        st("s2", "Eq(2*x, 10 - y)", K.EQUATION, R.EQUIVALENT, ["s1"]),
    ]
    verdict = run(load_subject("general"), steps).by_id()["s2"]
    assert verdict.status is S.UNVERIFIABLE and "crash" in verdict.method_used
