"""Relation dispatch shared by the kind strategies.

The kind decides *how* two things are compared; the relation decides *what* is
compared against what. A subclass normally only overrides `compare`.
See ADR 0003.
"""

from __future__ import annotations

from typing import Any

import sympy

from app.schemas import Step, StepKind, StepRelation, StepVerification, VerificationStatus
from app.subjects.loader import SubjectConfig
from app.verification.equivalence import (
    Judgement,
    Outcome,
    expr_equivalence,
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

        # Prefer whichever reading reached a definite answer.
        if pinned.outcome is Outcome.DIFFERENT and satisfied.outcome is Outcome.DIFFERENT:
            return pinned
        return pinned if satisfied.outcome is Outcome.INCONCLUSIVE else satisfied

    def check_result(self, step: Step, ctx: VerifyContext, current: Any) -> Judgement:
        """A `result` step is checked against the oldest symbolic ancestor --
        the original equation -- rather than against the step just before it."""
        roots = [
            ctx.parsed_of(a.id)
            for a in reversed(ctx.ancestors(step))
            if ctx.parsed_of(a.id) is not None
        ]
        if not roots:
            return Judgement(Outcome.INCONCLUSIVE, "result", "no hay ecuación original que usar")
        return satisfies(current, roots[0], ctx.subject)

    # --- dispatch ---------------------------------------------------------

    def verify(self, step: Step, ctx: VerifyContext) -> StepVerification:
        current = ctx.parsed_of(step.id)
        if current is None:
            return unverifiable(
                step,
                self.name,
                ctx.parse_errors.get(step.id, "el paso no se pudo interpretar"),
            )

        parents = ctx.parsed_parents(step)

        if step.relation is StepRelation.ASSERTION:
            return unverifiable(
                step,
                self.name,
                "Afirmación nueva: no se deriva de un paso anterior, así que solo la "
                "revisó el modelo.",
            )

        if step.relation is StepRelation.RESULT:
            return from_judgement(step, self.check_result(step, ctx, current), "resultado")

        if not parents:
            return unverifiable(
                step,
                self.name,
                "No se pudo comprobar: el paso no indica de cuál anterior proviene.",
            )

        parent = parents[0]

        if step.relation is StepRelation.SPECIALIZATION:
            return from_judgement(
                step, self.check_specialization(current, parent, ctx.subject), "especialización"
            )

        if step.relation is StepRelation.SUBSTITUTION:
            subs = collect_substitutions(step, ctx)
            target = parent.subs(subs) if subs else parent
            judgement = self.compare(target, current, ctx.subject)
            if judgement.outcome is Outcome.DIFFERENT and not subs:
                judgement = Judgement(
                    Outcome.INCONCLUSIVE,
                    judgement.method,
                    "el paso sustituye valores que no aparecen en pasos anteriores",
                )
            return from_judgement(step, judgement, "sustitución")

        # EQUIVALENT
        judgement = self.compare(parent, current, ctx.subject)
        if judgement.outcome is Outcome.DIFFERENT:
            # The model may have mislabelled a specialization as an equivalence.
            # Retry before declaring an error, so a mislabelled relation does not
            # produce a false cross (ADR 0003).
            retry = satisfies(current, parent, ctx.subject)
            if retry.is_equivalent:
                return correct(
                    step,
                    f"{self.name}+substitute",
                    "No es una equivalencia, pero sí satisface el paso anterior: "
                    "se leyó como un caso particular.",
                )
        return from_judgement(step, judgement, "equivalencia")
