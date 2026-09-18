"""A `given` step is a premise, not a derivation (ADR 0003)."""

from __future__ import annotations

from app.schemas import Step, StepKind, StepRelation, StepVerification
from app.verification.registry import VerifyContext, register
from app.verification.strategies.base import correct


class GivenStrategy:
    name = "given"
    # Lowest priority number: a given wins over every kind-based strategy,
    # because there is nothing to compare it against whatever its kind.
    priority = 10
    kinds = frozenset(StepKind)
    always_enabled = True

    def applies(self, step: Step, ctx: VerifyContext) -> bool:
        del ctx
        return step.relation is StepRelation.GIVEN

    def verify(self, step: Step, ctx: VerifyContext) -> StepVerification:
        del ctx
        return correct(step, "given", "Dato del problema: no hay nada que comprobar.")


register(GivenStrategy())
