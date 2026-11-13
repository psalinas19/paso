"""Relation dispatch shared by the kind strategies.

The kind decides *how* two things are compared; the relation decides *what* is
compared against what. A subclass normally only overrides `compare`.
See ADR 0003.
"""

from __future__ import annotations

from typing import Any

import sympy
from sympy.core.function import AppliedUndef

from app.schemas import Step, StepKind, StepRelation, StepVerification, VerificationStatus
from app.subjects.loader import SubjectConfig
from app.verification.equivalence import (
    UNEVALUATED,
    Judgement,
    Outcome,
    as_difference,
    equation_equivalence,
    expr_equivalence,
    names,
    satisfies,
    specializes,
)
from app.verification.registry import VerifyContext


def unverifiable(step: Step, method: str, detail: str) -> StepVerification:
    return StepVerification(
        step_id=step.id,
        status=VerificationStatus.UNVERIFIABLE,
        detail=detail,
        method_used=method,
    )


def correct(step: Step, method: str, detail: str) -> StepVerification:
    return StepVerification(
        step_id=step.id,
        status=VerificationStatus.CORRECT,
        detail=detail,
        method_used=method,
    )


def wrong(step: Step, method: str, detail: str) -> StepVerification:
    return StepVerification(
        step_id=step.id,
        status=VerificationStatus.ERROR,
        detail=detail,
        method_used=method,
    )


def from_judgement(step: Step, judgement: Judgement, context: str) -> StepVerification:
    """Map an Outcome onto the three states of SPEC 2.4.

    INCONCLUSIVE always becomes `unverifiable`, never `error`: not being able to
    decide is our limitation, not the student's mistake (ADR 0004).
    """
    if judgement.outcome is Outcome.EQUIVALENT:
        detail = judgement.detail or f"{context}: coincide."
        return correct(step, judgement.method, detail)
    if judgement.outcome is Outcome.DIFFERENT:
        detail = judgement.detail or f"{context}: no coincide."
        return wrong(step, judgement.method, f"No se sostiene. {detail}")
    return unverifiable(
        step,
        judgement.method,
        f"No se pudo comprobar simbólicamente. {judgement.detail}".strip(),
    )


def preceding(step: Step, ctx: VerifyContext) -> list[Step]:
    """Steps written before this one, in reading order.

    Wider than `ancestors` on purpose. The data of a problem is written at the
    top of the page and is a premise of the whole development, not of one
    branch of it, so a given is rarely in any step's derives_from chain.
    """
    try:
        index = ctx.order.index(step.id)
    except ValueError:
        return []
    return [ctx.steps[sid] for sid in ctx.order[:index] if sid in ctx.steps]


def collect_substitutions(step: Step, ctx: VerifyContext) -> dict[Any, Any]:
    """Values stated as givens earlier on the page, e.g. Eq(R_1, 100).

    These are what a `substitution` step is allowed to plug in.
    """
    subs: dict[Any, Any] = {}
    for earlier in preceding(step, ctx):
        if earlier.relation is not StepRelation.GIVEN:
            continue
        parsed = ctx.parsed_of(earlier.id)
        for item in parsed if isinstance(parsed, list) else [parsed]:
            if isinstance(item, sympy.Equality) and item.lhs not in subs:
                subs[item.lhs] = item.rhs
    return subs


def _items(parsed: Any) -> list[Any]:
    return list(parsed) if isinstance(parsed, list | tuple) else [parsed]


def substitute(obj: Any, values: dict[Any, Any]) -> Any:
    """`obj` with the known values put in; works on a system as on one equation.

    Applied a few times over, so V = i*R, i = 2, R = 5 ends up as V = 10.
    """
    if not values:
        return obj
    if isinstance(obj, list | tuple):
        return [substitute(item, values) for item in obj]
    if not isinstance(obj, sympy.Basic):
        return obj
    for _ in range(4):
        replaced = obj.subs(values)
        if replaced == obj:
            break
        obj = replaced
    return obj


def known_values(step: Step, ctx: VerifyContext, current: Any) -> dict[Any, Any]:
    """What earlier lines of the page say a symbol is worth: `R = 5`, `x = 3`.

    Wider than `collect_substitutions`: a value computed two lines up is as
    usable as one given in the statement. A symbol the page gives two different
    numbers for (the two roots of a quadratic) is left out as ambiguous, and so
    is whatever the current step itself is solving for.
    """
    solving_for = {item.lhs for item in _items(current) if isinstance(item, sympy.Equality)}
    seen: dict[Any, list[Any]] = {}
    for earlier in preceding(step, ctx):
        for item in _items(ctx.parsed_of(earlier.id)):
            if (
                isinstance(item, sympy.Equality)
                and isinstance(item.lhs, sympy.Symbol)
                and not item.rhs.has(item.lhs)
                and item.lhs not in solving_for
            ):
                seen.setdefault(item.lhs, []).append(item.rhs)

    values: dict[Any, Any] = {}
    for symbol, candidates in seen.items():
        numbers = [c for c in candidates if c.is_number]
        if len({sympy.nsimplify(n) for n in numbers}) > 1:
            continue  # two different numbers: not ours to pick
        values[symbol] = numbers[-1] if numbers else candidates[-1]
    return values


def identity_judgement(current: Any, subject: SubjectConfig) -> Judgement | None:
    """A line that states the value of an operation, checked on its own.

    `Integral(2*x, (x, 0, 3)) = 9` or the inverse transform of 3/(s**2 + 9)
    being sin(3t) is true or false whatever came before it, so the relation the
    model assigned does not matter. Returns None when the line is not of that
    shape or SymPy cannot carry the operation out.
    """
    # Imported here: the expression strategy itself builds on this module.
    from app.verification.strategies.expression import (
        evaluate_operations,
        integration_constant_judgement,
    )

    if not isinstance(current, sympy.Equality) or current.atoms(AppliedUndef):
        return None
    for operation, claimed in ((current.lhs, current.rhs), (current.rhs, current.lhs)):
        if not isinstance(operation, UNEVALUATED) or claimed.atoms(*UNEVALUATED):
            # Two integrals set equal (separating variables) is an equation to
            # be solved, not a claim about the value of either.
            continue
        constant = integration_constant_judgement(operation, claimed)
        if constant is not None:
            return constant
        done, value = evaluate_operations(operation), evaluate_operations(claimed)
        if done.atoms(*UNEVALUATED) or value.atoms(*UNEVALUATED):
            return None  # SymPy could not do it: not ours to call
        verdict = expr_equivalence(done, value, subject)
        return Judgement(verdict.outcome, "identity", verdict.detail)
    return None


def definition_judgement(parent: Any, current: Any, subject: SubjectConfig) -> Judgement | None:
    """`f(x) = sin(x**2)` followed by a line about f, typically its derivative.

    Putting the definition into the new line turns it into a plain identity,
    which is how a forgotten chain rule is caught.
    """
    if not (isinstance(parent, sympy.Equality) and isinstance(parent.lhs, AppliedUndef)):
        return None
    if not isinstance(current, sympy.Equality) or parent.rhs.atoms(AppliedUndef):
        return None
    mentions = current.atoms(sympy.Derivative) | current.atoms(sympy.Integral)
    if not any(node.has(parent.lhs) for node in mentions):
        return None
    verdict = satisfies(parent, current, subject)
    if verdict.outcome is Outcome.INCONCLUSIVE:
        return None
    return Judgement(verdict.outcome, "definition", verdict.detail)


def _plain_equations(parsed_steps: list[Any]) -> list[Any] | None:
    """The equations of some steps, if all of them are ordinary algebra."""
    equations = [item for parsed in parsed_steps for item in _items(parsed)]
    for equation in equations:
        if not isinstance(equation, sympy.Equality):
            return None
        if equation.atoms(AppliedUndef) or equation.atoms(*UNEVALUATED):
            return None
    return equations


def _holds(claim: Any, values: dict[Any, Any], subject: SubjectConfig) -> bool | None:
    """Whether an equation is true at these values, allowing for rounding by hand."""
    try:
        left = complex(sympy.N(claim.lhs.subs(values)))
        right = complex(sympy.N(claim.rhs.subs(values)))
    except (TypeError, ValueError):
        return None
    return abs(left - right) <= subject.tolerance.hand_rounding * max(1.0, abs(left), abs(right))


def consequence_judgement(
    parents: list[Any], current: Any, subject: SubjectConfig
) -> Judgement | None:
    """A step that comes out of a system with one solution: nodal and mesh
    analysis, two equations added together, a value read off a solved system.

    When the steps it derives from pin every unknown to a number, the new line
    either holds at those numbers or it does not follow from them.
    """
    system = _plain_equations(parents)
    claims = _plain_equations([current])
    if not system or not claims:
        return None
    unknowns = sorted(set().union(*(eq.free_symbols for eq in system)), key=lambda s: s.name)
    if len(unknowns) < 2 or len(system) < len(unknowns):
        return None  # one unknown is the roots check; fewer equations cannot pin them
    try:
        solutions = sympy.solve(system, unknowns, dict=True)
    except Exception:  # noqa: BLE001
        return None
    if len(solutions) != 1 or set(solutions[0]) != set(unknowns):
        return None
    solution = solutions[0]
    if not all(value.is_number for value in solution.values()):
        return None
    if not all(claim.free_symbols <= set(unknowns) for claim in claims):
        return None
    verdicts = [_holds(claim, solution, subject) for claim in claims]
    if any(v is None for v in verdicts):
        return None
    if all(verdicts):
        return Judgement(
            Outcome.EQUIVALENT,
            "system-solution",
            "se cumple con la solución de los pasos anteriores",
        )
    return Judgement(
        Outcome.DIFFERENT, "system-solution", "no se cumple con la solución de los pasos anteriores"
    )


def coefficients_judgement(parent: Any, current: Any, subject: SubjectConfig) -> Judgement | None:
    """`A = -1` after `2*s + 1 = A*(s + 2) + B*(s + 1)`: partial fractions and
    undetermined coefficients, where an identity in the variable fixes the letters."""
    if not isinstance(parent, sympy.Equality) or parent.atoms(AppliedUndef, *UNEVALUATED):
        return None
    variables = [
        symbol for symbol in parent.free_symbols if symbol.name in {*subject.independent_vars, "s"}
    ]
    if len(variables) != 1:
        return None
    variable = variables[0]
    letters = sorted(parent.free_symbols - {variable}, key=lambda s: s.name)
    claims = _items(current)
    if not letters or not all(
        isinstance(claim, sympy.Equality) and claim.lhs in letters and claim.rhs.is_number
        for claim in claims
    ):
        return None
    try:
        fixed = sympy.solve_undetermined_coeffs(as_difference(parent), letters, variable)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(fixed, list):
        fixed = fixed[0] if len(fixed) == 1 else None
    if not fixed or set(fixed) != set(letters):
        return None
    if all(_holds(claim, fixed, subject) for claim in claims):
        return Judgement(Outcome.EQUIVALENT, "coefficients", "igualando coeficientes da ese valor")
    wrong_one = next(claim for claim in claims if not _holds(claim, fixed, subject))
    return Judgement(
        Outcome.DIFFERENT,
        "coefficients",
        f"igualando coeficientes, {wrong_one.lhs} = {fixed[wrong_one.lhs]}",
    )


def roots_judgement(parent: Any, current: Any, subject: SubjectConfig) -> Judgement | None:
    """`r_1 = -1`, `r_2 = -2` after `r**2 + 3*r + 2 = 0`: are those its roots?

    Compared as equations they look unrelated -- the roots are given new names
    -- which is how a correct characteristic equation used to earn a cross.
    """
    if (
        not isinstance(parent, sympy.Equality)
        or parent.atoms(AppliedUndef)
        or parent.atoms(*UNEVALUATED)
        or len(parent.free_symbols) != 1
    ):
        return None
    (unknown,) = parent.free_symbols
    claims = _items(current)
    for claim in claims:
        if not (
            isinstance(claim, sympy.Equality)
            and isinstance(claim.lhs, sympy.Symbol)
            and (claim.lhs == unknown or claim.lhs.name.startswith(f"{unknown.name}_"))
            and not claim.rhs.free_symbols
        ):
            return None
    try:
        roots = sympy.solve(parent, unknown)
    except Exception:  # noqa: BLE001
        return None
    if not roots:
        return None

    def is_root(value: Any) -> bool:
        for root in roots:
            try:
                gap = abs(complex(sympy.N(value - root)))
                size = max(1.0, abs(complex(sympy.N(root))))
            except (TypeError, ValueError):
                continue
            # Roots are often rounded by hand: 1.41 for sqrt(2).
            if gap <= subject.tolerance.hand_rounding * size:
                return True
        return False

    strangers = [claim for claim in claims if not is_root(claim.rhs)]
    if strangers:
        wrong_one = strangers[0]
        return Judgement(
            Outcome.DIFFERENT,
            "roots",
            f"{wrong_one.lhs} = {wrong_one.rhs} no es solución de la ecuación anterior",
        )
    return Judgement(Outcome.EQUIVALENT, "roots", "son soluciones de la ecuación anterior")


def initial_condition_judgement(
    step: Step, ctx: VerifyContext, parent: Any, current: Any
) -> Judgement | None:
    """`C1 = 1` after `y = C1*cos(x) + C2*sin(x)`, with `y(0) = 1` on the page."""
    if not (
        isinstance(parent, sympy.Equality)
        and isinstance(parent.lhs, AppliedUndef)
        and len(parent.lhs.args) == 1
    ):
        return None
    variable, function = parent.lhs.args[0], parent.lhs.func
    constants = parent.rhs.free_symbols - {variable}
    fixed = {}
    for claim in _items(current):
        if not (isinstance(claim, sympy.Equality) and claim.lhs in constants):
            return None
        fixed[claim.lhs] = claim.rhs

    conditions = [
        (item, parent.rhs.subs(variable, item.lhs.args[0]) - item.rhs)
        for earlier in preceding(step, ctx)
        for item in _items(ctx.parsed_of(earlier.id))
        if isinstance(item, sympy.Equality)
        and isinstance(item.lhs, AppliedUndef)
        and item.lhs.func == function
        and len(item.lhs.args) == 1
        and item.lhs.args[0].is_number
    ]
    for condition, constraint in conditions:
        try:
            left = sympy.simplify(constraint.subs(fixed))
        except Exception:  # noqa: BLE001
            continue
        said = f"{condition.lhs} = {condition.rhs}"
        if left == 0:
            return Judgement(Outcome.EQUIVALENT, "initial-condition", f"cumple {said}")
        if left.is_number:
            return Judgement(Outcome.DIFFERENT, "initial-condition", f"no cumple {said}")
    return None


def trial_judgement(step: Step, ctx: VerifyContext, parents: list[Any], current: Any) -> Any:
    """A trial solution put into its differential equation (undetermined
    coefficients): `y_p = A*exp(2x)` into `y'' - y = exp(2x)`. Can only confirm."""

    def differential(item: Any) -> bool:
        return isinstance(item, sympy.Equality) and bool(item.atoms(sympy.Derivative))

    trial = next(
        (
            p
            for p in parents
            if isinstance(p, sympy.Equality)
            and isinstance(p.lhs, sympy.Symbol | AppliedUndef)
            and not p.atoms(sympy.Derivative)
        ),
        None,
    )
    if trial is None:
        return None
    equations = [p for p in parents if differential(p)] + [
        ctx.parsed_of(e.id)
        for e in preceding(step, ctx)
        if e.relation is StepRelation.GIVEN and differential(ctx.parsed_of(e.id))
    ]
    for equation in equations:
        unknowns = {
            d.expr for d in equation.atoms(sympy.Derivative) if isinstance(d.expr, AppliedUndef)
        }
        if len(unknowns) != 1:
            continue
        try:
            filled = equation.subs(unknowns.pop(), trial.rhs).doit()
        except Exception:  # noqa: BLE001
            continue
        if equation_equivalence(filled, current, ctx.subject).is_equivalent:
            return Judgement(
                Outcome.EQUIVALENT, "trial", "es la solución propuesta sustituida en la ecuación"
            )
    return None


def laplace_judgement(parent: Any, current: Any, subject: SubjectConfig) -> Judgement | None:
    """A step that crosses between the s domain and the t domain.

    F(s) = 1/(s*(s + 1)) followed by f(t) = 1 - exp(-t): transform the time
    side and compare in s, where everything is a rational function. Only when
    the two lines are visibly a transform pair (F and f, Y and y) is a mismatch
    an error; otherwise the step may be something else, such as the response
    to an input that is not written down.
    """
    if "laplace" not in subject.strategies:
        return None
    t, s = sympy.Symbol("t"), sympy.Symbol("s")

    def value(item: Any) -> Any:
        if isinstance(item, sympy.Equality):
            return item.rhs if isinstance(item.lhs, sympy.Symbol | AppliedUndef) else None
        return item if isinstance(item, sympy.Basic) else None

    def domain(expr: Any) -> str | None:
        if expr is None or expr.atoms(AppliedUndef) or expr.atoms(*UNEVALUATED):
            return None
        has_t, has_s = t in expr.free_symbols, s in expr.free_symbols
        return "t" if has_t and not has_s else "s" if has_s and not has_t else None

    before, after = value(parent), value(current)
    crossing = (domain(before), domain(after))
    if crossing == ("s", "t"):
        in_time, in_s = after, before
    elif crossing == ("t", "s"):
        in_time, in_s = before, after
    else:
        return None
    try:
        transformed = sympy.LaplaceTransform(in_time, t, s).doit(noconds=True)
    except Exception:  # noqa: BLE001
        return None
    if transformed.atoms(sympy.LaplaceTransform):
        return None
    verdict = expr_equivalence(transformed, in_s, subject)
    if verdict.is_equivalent:
        return Judgement(Outcome.EQUIVALENT, "laplace", "la transformada de Laplace coincide")

    def label(item: Any) -> str | None:
        if isinstance(item, sympy.Equality) and isinstance(item.lhs, AppliedUndef):
            return item.lhs.func.__name__.lower()
        return None

    paired = label(parent) is not None and label(parent) == label(current)
    if verdict.outcome is Outcome.DIFFERENT and paired:
        return Judgement(
            Outcome.DIFFERENT,
            "laplace",
            f"su transformada de Laplace es {transformed}, no la expresión del paso anterior",
        )
    return None


#: Verdicts of "these two are not the same statement". A mismatch found this
#: way is only an error if the two steps were talking about the same things.
_COMPARISONS = frozenset(
    {"numeric", "simplify", "structural", "proportional", "equation", "solve", "system"}
)


class KindStrategy:
    """Base for the per-kind strategies. Subclasses override `compare`."""

    name: str = "base"
    priority: int = 100
    kinds: frozenset[StepKind] = frozenset()
    always_enabled: bool = False

    def applies(self, step: Step, ctx: VerifyContext) -> bool:
        del ctx
        return step.kind in self.kinds and step.is_symbolic

    # --- overridable ------------------------------------------------------

    def compare(self, parent: Any, current: Any, subject: SubjectConfig) -> Judgement:
        return expr_equivalence(parent, current, subject)

    def check_specialization(self, current: Any, parent: Any, subject: SubjectConfig) -> Judgement:
        """Two readings of "a condition was imposed", tried in order.

        Either the step pins down a free constant of the previous step
        (y = C1 e^x becomes y = 3 e^x), or it is a candidate that has to satisfy
        the previous step outright (a solution checked against its equation).
        Only if neither holds is it an error.
        """
        pinned = specializes(parent, current, subject)
        if pinned.is_equivalent:
            return pinned

        satisfied = satisfies(current, parent, subject)
        if satisfied.is_equivalent:
            return satisfied

        # An error needs one reading to say "wrong" and the other not to
        # disagree; if either could not decide, neither can we.
        if pinned.outcome is Outcome.INCONCLUSIVE:
            return pinned
        return pinned if satisfied.outcome is Outcome.DIFFERENT else satisfied

    def result_targets(self, step: Step, ctx: VerifyContext) -> list[Any]:
        """What a `result` has to satisfy, most authoritative first: the
        problem data in reading order (CLAUDE.md, rule 5), then the steps it
        was derived from, oldest first."""
        earlier = preceding(step, ctx)
        ancestors = {a.id for a in ctx.ancestors(step)}
        data = [e for e in earlier if e.relation is StepRelation.GIVEN]
        derived = [e for e in earlier if e.id in ancestors and e.relation is not StepRelation.GIVEN]
        return [
            item
            for candidate in [*data, *derived]
            for item in _items(ctx.parsed_of(candidate.id))
            if isinstance(item, sympy.Equality)
        ]

    def check_result(self, step: Step, ctx: VerifyContext, current: Any) -> Judgement:
        """A `result` is checked against the original equation rather than
        against whatever step happens to precede it."""
        verdict = Judgement(Outcome.INCONCLUSIVE, "result", "no hay ecuación original que usar")
        if not isinstance(current, sympy.Equality):
            return verdict
        for target in self.result_targets(step, ctx):
            if not as_difference(target).has(current.lhs):
                continue
            verdict = satisfies(current, target, ctx.subject)
            if verdict.outcome is not Outcome.INCONCLUSIVE:
                return verdict
        return verdict

    def settle(
        self,
        step: Step,
        ctx: VerifyContext,
        parents: list[Any],
        parent: Any,
        current: Any,
        verdict: Judgement,
    ) -> Judgement:
        """Second look at a "these differ" before it becomes a cross.

        Comparing a step with the one before it only proves a mistake when the
        step used nothing else. It routinely does: a value from three lines up,
        a second parent, a name it introduces, a condition from the statement.
        In each of those cases the comparison was the wrong question, and the
        honest answer is "could not check" (CLAUDE.md, rule 1).
        """
        subject = ctx.subject
        values = known_values(step, ctx, current)
        if values:
            filled_parent, filled = substitute(parent, values), substitute(current, values)
            comparable = all(
                isinstance(item, sympy.Basic)
                and not isinstance(item, sympy.logic.boolalg.Boolean)
                or isinstance(item, sympy.Equality)
                for item in [*_items(filled_parent), *_items(filled)]
            )
            if comparable and (filled_parent != parent or filled != current):
                again = self.compare(filled_parent, filled, subject)
                if again.is_equivalent:
                    return Judgement(
                        Outcome.EQUIVALENT,
                        f"{again.method}+values",
                        "coincide al usar los valores de pasos anteriores",
                    )
                parent, current = filled_parent, filled

        def doubt(reason: str) -> Judgement:
            return Judgement(Outcome.INCONCLUSIVE, verdict.method, reason)

        before, after = names(parent), names(current)
        brought_in = sorted(after - before)
        if brought_in:
            return doubt(
                f"el paso usa {', '.join(brought_in)}, que no aparece en el paso del que sale"
            )
        if len(parents) > 1:
            return doubt("el paso sale de varios anteriores y no se pudo comprobar contra todos")

        if verdict.method == "specialize":
            return verdict  # dropping the constant is what a specialization does

        dropped = before - after
        if dropped and verdict.method in _COMPARISONS:
            try:
                ratio = sympy.simplify(as_difference(parent) / as_difference(current))
                if ratio != 0 and ratio.is_finite is not False and names(ratio) <= dropped:
                    return Judgement(
                        Outcome.EQUIVALENT,
                        "proportional",
                        f"es el paso anterior dividido entre {ratio}",
                    )
            except Exception:  # noqa: BLE001 - systems, or a division SymPy cannot do
                pass
            gone = ", ".join(sorted(dropped))
            return doubt(f"en el paso ya no aparece {gone} y la hoja no dice cuánto vale")
        return verdict

    # --- dispatch ---------------------------------------------------------

    def verify(self, step: Step, ctx: VerifyContext) -> StepVerification:
        current = ctx.parsed_of(step.id)
        if current is None:
            return unverifiable(
                step,
                self.name,
                ctx.parse_errors.get(step.id, "el paso no se pudo interpretar"),
            )
        subject = ctx.subject

        # A line that states the value of an integral, a derivative or a
        # transform stands or falls on its own, whatever relation it was given.
        own = identity_judgement(current, subject)
        if own is not None and own.outcome is not Outcome.INCONCLUSIVE:
            return from_judgement(step, own, "operación")

        parents = ctx.parsed_parents(step)

        if step.relation is StepRelation.ASSERTION:
            return unverifiable(
                step,
                self.name,
                "Afirmación nueva: no se deriva de un paso anterior, así que solo la "
                "revisó el modelo.",
            )

        if not parents:
            if step.relation is StepRelation.RESULT:
                return from_judgement(step, self.check_result(step, ctx, current), "resultado")
            return unverifiable(
                step,
                self.name,
                "No se pudo comprobar: el paso no indica de cuál anterior proviene.",
            )

        parent = parents[0]

        # Kinds of step with a check of their own, tried before any comparison.
        for special in (
            roots_judgement(parent, current, subject),
            consequence_judgement(parents, current, subject),
            coefficients_judgement(parent, current, subject),
            definition_judgement(parent, current, subject),
            initial_condition_judgement(step, ctx, parent, current),
            laplace_judgement(parent, current, subject),
            trial_judgement(step, ctx, parents, current),
        ):
            if special is not None and special.outcome is not Outcome.INCONCLUSIVE:
                return from_judgement(step, special, "comprobación")

        if step.relation is StepRelation.RESULT:
            verdict = self.check_result(step, ctx, current)
            if verdict.outcome is not Outcome.INCONCLUSIVE:
                return from_judgement(step, verdict, "resultado")
            # Nothing to substitute it into: then it is the last step of the
            # chain, and is checked as one.

        if step.relation is StepRelation.SPECIALIZATION:
            verdict = self.check_specialization(current, parent, subject)
            context = "especialización"
        elif step.relation is StepRelation.SUBSTITUTION:
            subs = collect_substitutions(step, ctx)
            verdict = self.compare(substitute(parent, subs), current, subject)
            context = "sustitución"
        else:
            verdict = self.compare(parent, current, subject)
            context = "equivalencia"

        if not verdict.is_equivalent:
            # The model may have mislabelled a specialization as an equivalence.
            # Retry before deciding, so a mislabelled relation does not produce
            # a false cross (ADR 0003).
            retry = satisfies(current, parent, subject)
            if retry.is_equivalent:
                return correct(
                    step,
                    f"{self.name}+substitute",
                    "No es una equivalencia, pero sí satisface el paso anterior: "
                    "se leyó como un caso particular.",
                )
        if verdict.outcome is Outcome.DIFFERENT:
            verdict = self.settle(step, ctx, parents, parent, current, verdict)
        return from_judgement(step, verdict, context)
