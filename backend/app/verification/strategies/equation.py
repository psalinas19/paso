"""Equations: same solution set, or (lhs - rhs) proportional by a nonzero
factor (SPEC 6.3). Comparing them as plain expressions would be wrong, because
multiplying both sides by a constant is a legitimate move."""

from __future__ import annotations

from typing import Any

from app.schemas import StepKind
from app.subjects.loader import SubjectConfig
from app.verification.equivalence import Judgement, Outcome, equation_equivalence
from app.verification.registry import register
from app.verification.strategies.base import KindStrategy
from app.verification.strategies.expression import (
    evaluate_operations,
    integration_constant_judgement,
)


class EquationStrategy(KindStrategy):
    name = "equation"
    priority = 50
    kinds = frozenset({StepKind.EQUATION})

    def compare(self, parent: Any, current: Any, subject: SubjectConfig) -> Judgement:
        # See the note in ExpressionStrategy.compare: this has to come first, or
        # "integrate both sides" followed by a correct "+ C1" reads as an error.
        constant = integration_constant_judgement(parent, current)
        if constant is not None:
            return constant

        direct = equation_equivalence(parent, current, subject)
        if direct.is_equivalent:
            return direct

        done = equation_equivalence(
            evaluate_operations(parent), evaluate_operations(current), subject
        )
        if done.is_equivalent:
            return done
        return done if direct.outcome is Outcome.INCONCLUSIVE else direct


register(EquationStrategy())
