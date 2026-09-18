"""The permanent test bank (SPEC 10).

One directory per case under backend/eval/cases/:

    <case-id>/
      image.jpg     the photo
      meta.yaml     subject, topic, provenance
      truth.json    the correct transcription, plus what the verifier should say

truth.json is written by hand, in the dialect of ADR 0002. That is the boring
work of phase 0 and there is no shortcut: without annotated truth there is
nothing to measure against.

The bank grows every semester with the new subjects (SPEC 10).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.config import EVAL_CASES_DIR
from app.schemas import Step, StepKind, StepRelation, VerificationStatus

IMAGE_NAMES = ("image.jpg", "image.jpeg", "image.png", "image.heic")


class SeededError(BaseModel):
    """A mistake deliberately present in the photo."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(description="Slug from the subject's error taxonomy, e.g. 'sign'.")
    verifiable: bool = Field(
        description="Whether a symbolic verifier can catch it at all. A misstated "
        "KCL equation cannot be (SPEC 3), and counting it against the verifier "
        "would measure the wrong thing. Reported separately (ADR 0004).",
    )
    note: str = ""


class TruthStep(BaseModel):
    """One step as it should have been read, and how it should be judged."""

    model_config = ConfigDict(extra="forbid")

    id: str
    latex: str = ""
    sympy: str | None = None
    kind: StepKind
    relation: StepRelation
    derives_from: list[str] = Field(default_factory=list)
    expected_status: VerificationStatus = VerificationStatus.CORRECT
    seeded_error: SeededError | None = None

    def as_step(self) -> Step:
        return Step(
            id=self.id,
            latex=self.latex,
            sympy=self.sympy,
            kind=self.kind,
            relation=self.relation,
            derives_from=self.derives_from,
            confidence=1.0,
        )


class CaseTruth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    steps: list[TruthStep]


class CaseMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    subject: str
    topic: str = ""
    source: str = ""
    notes: str = ""


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    meta: CaseMeta
    truth: CaseTruth
    image_path: Path

    @property
    def id(self) -> str:
        return self.meta.id

    @property
    def seeded_errors(self) -> list[TruthStep]:
        return [s for s in self.truth.steps if s.seeded_error is not None]


class MalformedCaseError(ValueError):
    pass


def load_case(directory: Path) -> EvalCase:
    meta_path = directory / "meta.yaml"
    truth_path = directory / "truth.json"

    if not meta_path.is_file() or not truth_path.is_file():
        raise MalformedCaseError(f"{directory.name}: faltan meta.yaml o truth.json.")

    image_path = next(
        (directory / name for name in IMAGE_NAMES if (directory / name).is_file()), None
    )
    if image_path is None:
        raise MalformedCaseError(
            f"{directory.name}: no hay imagen (se esperaba una de {', '.join(IMAGE_NAMES)})."
        )

    meta = CaseMeta.model_validate(yaml.safe_load(meta_path.read_text(encoding="utf-8")))
    truth = CaseTruth.model_validate_json(truth_path.read_text(encoding="utf-8"))
    return EvalCase(meta=meta, truth=truth, image_path=image_path)


def load_cases(cases_dir: Path | None = None) -> list[EvalCase]:
    base = cases_dir if cases_dir is not None else EVAL_CASES_DIR
    if not base.is_dir():
        return []
    cases = []
    for directory in sorted(p for p in base.iterdir() if p.is_dir()):
        cases.append(load_case(directory))
    return cases
