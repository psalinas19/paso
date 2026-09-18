"""Subject configuration: the mechanism that makes adding a subject a file, not code.

A subject declares its notation, which verification strategies it uses, its
numeric tolerances and its error taxonomy. Adding "Senales y Sistemas" next
semester means dropping a YAML file here (SPEC 12.5).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.config import SUBJECTS_DIR


class ErrorType(BaseModel):
    """One entry of the per-subject error taxonomy (SPEC 6.6). Labels are the
    Spanish text shown in the UI; ids are stable slugs used in stored data."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str = ""


class NumericTolerance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    absolute: float = 1e-9
    relative: float = 1e-6
    #: Iterative methods are checked against the student's own previous value,
    #: so rounding they did by hand has to be tolerated. Overridden per subject.
    hand_rounding: float = 5e-3


class SubjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    notation: str = Field(default="", description="e.g. 'Hayt' for Circuitos.")

    complex_domain: bool = Field(
        default=False,
        description="When true, 'j' parses as the imaginary unit and bare 'I' is "
        "forbidden as a symbol name. See ADR 0002.",
    )
    independent_vars: list[str] = Field(default_factory=lambda: ["x"])
    extra_functions: list[str] = Field(
        default_factory=list,
        description="Callables allowed on top of the base whitelist in safe_parse.",
    )

    strategies: list[str] = Field(
        default_factory=list,
        description="Which verification strategies this subject enables (SPEC 6.3).",
    )
    tolerance: NumericTolerance = Field(default_factory=NumericTolerance)

    topics: list[str] = Field(
        default_factory=list,
        description="Cross-subject topic tags, e.g. 'laplace', 'edo-lineal' (SPEC 12.6).",
    )
    error_types: list[ErrorType] = Field(default_factory=list)

    notation_notes: str = Field(
        default="",
        description="Injected into the recognition prompt: how I write this subject.",
    )
    tutor_notes: str = Field(
        default="",
        description="Injected into tutor prompts from phase 2 on.",
    )

    @property
    def forbidden_symbols(self) -> frozenset[str]:
        # In a complex-domain subject, 'I' is the imaginary unit, so a current
        # must be written I_1 / i_L and never bare 'I' (ADR 0002).
        return frozenset({"I"}) if self.complex_domain else frozenset()


class SubjectNotFoundError(LookupError):
    pass


def _config_path(slug: str) -> Path:
    return SUBJECTS_DIR / f"{slug.lower()}.yaml"


def load_subject(slug: str) -> SubjectConfig:
    path = _config_path(slug)
    if not path.is_file():
        available = ", ".join(sorted(available_subjects())) or "ninguna"
        raise SubjectNotFoundError(
            f"No existe la materia '{slug}'. Materias disponibles: {available}."
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return SubjectConfig.model_validate(data)


@lru_cache
def load_subject_cached(slug: str) -> SubjectConfig:
    return load_subject(slug)


def available_subjects() -> list[str]:
    if not SUBJECTS_DIR.is_dir():
        return []
    return sorted(p.stem for p in SUBJECTS_DIR.glob("*.yaml"))
