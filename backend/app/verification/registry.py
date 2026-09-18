"""Strategy registry (SPEC 6.3).

One strategy per kind, behind a common interface, so future semesters add
Laplace, transfer functions, state space, phasors or Fourier/Z as new files
without touching the existing ones. Each subject declares which strategies it
enables in its YAML config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.schemas import Step, StepKind, StepVerification
from app.subjects.loader import SubjectConfig


@dataclass
class VerifyContext:
    """Everything a strategy may look at while checking one step."""

    subject: SubjectConfig
    steps: dict[str, Step]
    order: list[str]
    parsed: dict[str, Any] = field(default_factory=dict)
    parse_errors: dict[str, str] = field(default_factory=dict)
    verdicts: dict[str, StepVerification] = field(default_factory=dict)

    def parents(self, step: Step) -> list[Step]:
        return [self.steps[pid] for pid in step.derives_from if pid in self.steps]

    def parsed_of(self, step_id: str) -> Any | None:
        return self.parsed.get(step_id)

    def parsed_parents(self, step: Step) -> list[Any]:
        return [
            self.parsed[pid]
            for pid in step.derives_from
            if pid in self.parsed and self.parsed[pid] is not None
        ]

    def ancestors(self, step: Step) -> list[Step]:
        """Transitive parents, nearest first, without cycles."""
        seen: set[str] = set()
        out: list[Step] = []
        frontier = list(step.derives_from)
        while frontier:
            sid = frontier.pop(0)
            if sid in seen or sid not in self.steps:
                continue
            seen.add(sid)
            parent = self.steps[sid]
            out.append(parent)
            frontier.extend(parent.derives_from)
        return out


@runtime_checkable
class Strategy(Protocol):
    """Common interface. `priority` orders selection, lowest first."""

    name: str
    priority: int
    kinds: frozenset[StepKind]
    always_enabled: bool

    def applies(self, step: Step, ctx: VerifyContext) -> bool: ...

    def verify(self, step: Step, ctx: VerifyContext) -> StepVerification: ...


_REGISTRY: list[Strategy] = []


def register(strategy: Strategy) -> Strategy:
    """Register a strategy instance. Called at import time by each module."""
    if any(s.name == strategy.name for s in _REGISTRY):
        raise ValueError(f"strategy '{strategy.name}' is already registered")
    _REGISTRY.append(strategy)
    _REGISTRY.sort(key=lambda s: s.priority)
    return strategy


def registered() -> list[Strategy]:
    return list(_REGISTRY)


def select(step: Step, ctx: VerifyContext) -> Strategy:
    """First enabled strategy that applies. Always terminates: the fallback
    strategy is always_enabled and applies to everything."""
    enabled = set(ctx.subject.strategies)
    for strategy in _REGISTRY:
        if not strategy.always_enabled and strategy.name not in enabled:
            continue
        if strategy.applies(step, ctx):
            return strategy
    raise RuntimeError("no strategy applied; the unverifiable fallback should have been reached")


def load_builtin_strategies() -> None:
    """Import the strategy modules so their register() calls run."""
    from app.verification.strategies import (  # noqa: F401
        equation,
        expression,
        given,
        numeric_iteration,
        ode,
        system,
        unverifiable,
    )
