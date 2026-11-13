"""Core contracts shared by recognition, verification and the eval harness.

These models are the stable boundary of the project. Everything else -- the CLIs
today, the FastAPI endpoints from phase 2 on -- is a thin wrapper over functions
that take and return these types. See docs/decisions/0001-fase0-scope.md.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Bumped whenever a stored shape changes incompatibly (SPEC 12.2).
SCHEMA_VERSION = 1

# Below this, the UI highlights the step and asks for confirmation (SPEC 6.2).
LOW_CONFIDENCE_THRESHOLD = 0.7


class StepKind(StrEnum):
    """Structural form of what is written, nothing else.

    Deliberately excludes "derivative"/"integral": those are operations inside a
    step, detected from the expression tree. See ADR 0003.
    """

    EXPRESSION = "expression"
    EQUATION = "equation"
    SYSTEM = "system"
    ODE = "ode"
    NUMERIC_ITERATION = "numeric_iteration"
    TEXT = "text"
    DIAGRAM = "diagram"


class StepRelation(StrEnum):
    """How a step relates to the ones it comes from -- picks the check to run.

    Declared by recognition rather than assumed, because "compare with the
    previous step" is wrong for givens, initial conditions, sibling KCL
    equations and numeric iterations. See ADR 0003.
    """

    GIVEN = "given"
    EQUIVALENT = "equivalent"
    SUBSTITUTION = "substitution"
    SPECIALIZATION = "specialization"
    ASSERTION = "assertion"
    RESULT = "result"


#: Relations that legitimately stand on their own, with no parent step.
ROOTLESS_RELATIONS = frozenset({StepRelation.GIVEN, StepRelation.ASSERTION})


class VerificationStatus(StrEnum):
    """The three states of SPEC 2.4. `depends_on_error` is a separate field,
    not a fourth state."""

    CORRECT = "correct"
    ERROR = "error"
    UNVERIFIABLE = "unverifiable"


class Step(BaseModel):
    """One transcribed step of a handwritten development."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable within one recognition, e.g. 's1'.")
    latex: str = Field(description="KaTeX-compatible, as written on paper.")
    sympy: str | None = Field(
        default=None,
        description="Parseable in the dialect of ADR 0002, or null when the step "
        "has no symbolic content (text, diagram, illegible).",
    )
    kind: StepKind
    relation: StepRelation
    derives_from: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    legible: bool = Field(
        default=True,
        description="False when the handwriting could not be read. The model marks "
        "it illegible instead of inventing content (SPEC 6.2).",
    )
    notes: str | None = None

    @field_validator("derives_from")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < LOW_CONFIDENCE_THRESHOLD

    @property
    def is_symbolic(self) -> bool:
        """Whether this step can even be checked symbolically."""
        return bool(self.sympy) and self.legible


class ImageMeta(BaseModel):
    """What was actually sent to the model -- feeds the latency/cost budget (D5)."""

    model_config = ConfigDict(extra="forbid")

    sha256: str
    media_type: str
    width: int
    height: int
    bytes_sent: int
    source_path: str | None = None


class Usage(BaseModel):
    """One paid call. Persisted as JSONL in phase 0, as UsageLog from phase 2."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    cache_hit: bool = False


class RecognitionResult(BaseModel):
    """Output of /recognize (SPEC 6.2), plus provenance for SPEC 12.3."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    subject: str
    steps: list[Step] = Field(default_factory=list)
    image: ImageMeta | None = None
    model: str = ""
    prompt_version: str = Field(
        default="",
        description="Hash of the prompt file, so a prompt edit is never silently "
        "untracked (SPEC 12.3, D8).",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Repairs applied to the model's output, e.g. a dangling "
        "derives_from reference. Surfaced in the eval report.",
    )
    usage: Usage | None = None

    @model_validator(mode="after")
    def _check_step_ids_unique(self) -> RecognitionResult:
        seen = [s.id for s in self.steps]
        if len(seen) != len(set(seen)):
            raise ValueError("step ids must be unique within a recognition")
        return self

    def by_id(self) -> dict[str, Step]:
        return {s.id: s for s in self.steps}

    @property
    def has_low_confidence(self) -> bool:
        return any(s.is_low_confidence for s in self.steps)


class StepVerification(BaseModel):
    """Result of checking one step (SPEC 6.3)."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    status: VerificationStatus
    detail: str = Field(description="Shown to the user, in Spanish.")
    method_used: str = Field(description="Which strategy ran, for debugging and eval.")
    depends_on_error: str | None = Field(
        default=None,
        description="Id of an upstream erroneous step this one is consistent with. "
        "Keeps a single error from painting the rest of the page red (ADR 0003).",
    )
    duration_ms: int = 0


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    subject: str
    steps: list[StepVerification] = Field(default_factory=list)

    def by_id(self) -> dict[str, StepVerification]:
        return {s.step_id: s for s in self.steps}

    @property
    def first_error(self) -> StepVerification | None:
        return next((s for s in self.steps if s.status is VerificationStatus.ERROR), None)

    def count(self, status: VerificationStatus) -> int:
        return sum(1 for s in self.steps if s.status is status)


class HintBasis(StrEnum):
    """What stands behind the step a hint points at (SPEC 9.4)."""

    #: The symbolic verifier proved the step does not follow.
    VERIFIED = "verified"
    #: Only the model thinks so, about a step the verifier could not check.
    MODEL_OPINION = "model_opinion"
    #: Nothing to point at.
    NONE = "none"


class Hint(BaseModel):
    """Level-1 help (SPEC 2.5): which step fails and a nudge, never the answer.

    The two sources are kept in separate fields so the UI can never blur them:
    `verified` is written by our code from the verifier's result; `hint` and
    the error classification are the model's words.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    step_id: str | None = None
    basis: HintBasis
    verified: str = Field(description="What was established symbolically. Spanish, ours.")
    hint: str = Field(default="", description="The model's nudge. Empty when there is none.")
    error_type: str | None = Field(
        default=None, description="Id from the subject's taxonomy, proposed by the model."
    )
    error_label: str | None = None
    model: str = ""
    prompt_version: str = ""
