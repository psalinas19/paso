"""Terminal fallback: text, diagrams, illegible handwriting and anything with
no symbolic content (SPEC 6.3). Always registered, always applies, always last,
so `select()` can never fail to find a strategy."""

from __future__ import annotations

from app.schemas import Step, StepKind, StepVerification
from app.verification.registry import VerifyContext, register
from app.verification.strategies.base import unverifiable

_REASONS = {
    StepKind.TEXT: "Es texto: no se verifica simbólicamente, solo lo revisó el modelo.",
    StepKind.DIAGRAM: ("Es un diagrama: no se verifica simbólicamente, solo lo comentó el modelo."),
}


class UnverifiableStrategy:
    name = "unverifiable"
    priority = 1000
    kinds = frozenset(StepKind)
    always_enabled = True

    def applies(self, step: Step, ctx: VerifyContext) -> bool:
        del step, ctx
        return True

    def verify(self, step: Step, ctx: VerifyContext) -> StepVerification:
        if not step.legible:
            return unverifiable(
                step, self.name, "No se pudo leer con claridad, así que no se verificó."
            )
        if step.kind in _REASONS:
            return unverifiable(step, self.name, _REASONS[step.kind])
        if not step.sympy:
            return unverifiable(
                step, self.name, "El paso no trae expresión simbólica que comprobar."
            )
        reason = ctx.parse_errors.get(step.id)
        if reason:
            return unverifiable(step, self.name, f"No se pudo interpretar: {reason}")
        return unverifiable(
            step,
            self.name,
            f"La materia no tiene una estrategia para pasos de tipo '{step.kind.value}'.",
        )


register(UnverifiableStrategy())
