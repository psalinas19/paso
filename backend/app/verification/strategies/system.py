"""Systems of equations: nodal and mesh analysis (SPEC 6.3).

What this can and cannot catch is worth being explicit about. Solving a system
wrongly is caught. A *wrongly stated* KCL equation is not: deciding whether the
currents at a node were summed correctly needs the circuit topology, and
structural recognition of diagrams is out of scope (SPEC 3). Those steps come
back as `unverifiable` and only the model comments on them. See ADR 0004.
"""

from __future__ import annotations

from typing import Any

import sympy

from app.schemas import StepKind
from app.subjects.loader import SubjectConfig
from app.verification.equivalence import Judgement, Outcome, solution_sets_match
from app.verification.registry import register
from app.verification.strategies.base import KindStrategy


def _as_equation_list(obj: Any) -> list[Any] | None:
    if isinstance(obj, list):
        return [e for e in obj if isinstance(e, sympy.Basic)]
    if isinstance(obj, sympy.Basic):
        return [obj]
    return None


def _unknowns(equations: list[Any]) -> list[sympy.Symbol]:
    symbols: set[sympy.Symbol] = set()
    for eq in equations:
        symbols |= eq.free_symbols
    return sorted(symbols, key=lambda s: s.name)


class SystemStrategy(KindStrategy):
    name = "system"
    priority = 45
    kinds = frozenset({StepKind.SYSTEM})

    def compare(self, parent: Any, current: Any, subject: SubjectConfig) -> Judgement:
        del subject
        parent_eqs = _as_equation_list(parent)
        current_eqs = _as_equation_list(current)
        if not parent_eqs or not current_eqs:
            return Judgement(Outcome.INCONCLUSIVE, "system", "no se pudo leer el sistema")

        unknowns = _unknowns(parent_eqs + current_eqs)
        if not unknowns:
            return Judgement(Outcome.INCONCLUSIVE, "system", "el sistema no tiene incógnitas")

        return solution_sets_match(parent_eqs, current_eqs, unknowns)


register(SystemStrategy())
