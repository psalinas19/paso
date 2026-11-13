"""The schema the model fills in (ADR 0005).

Deliberately flat and free of defaults: every field is required, so the model
has to decide `relation` and `derives_from` explicitly instead of letting a
default fill them in silently. Those two are the most fragile part of the
prompt (ADR 0003), and a silent default would hide that in the eval.

Kept separate from app.schemas.Step so the wire format the model sees can stay
stable while the internal model grows helpers.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import Step, StepKind, StepRelation


class RecognizedStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Sequential id for this step: s1, s2, s3...")
    latex: str = Field(description="The step exactly as written, KaTeX-compatible.")
    sympy: str | None = Field(
        description="The step in the SymPy dialect given in the instructions, or "
        "null if it has no symbolic content or could not be read."
    )
    kind: StepKind = Field(description="Structural form of what is written.")
    relation: StepRelation = Field(description="How this step relates to its sources.")
    derives_from: list[str] = Field(
        description="Ids of the steps this one comes from. Empty for a given or a "
        "standalone assertion."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="How sure you are that you read this step correctly."
    )
    legible: bool = Field(description="False if the handwriting could not be read.")
    notes: str | None = Field(
        description="Units, what was illegible, or anything worth flagging. Null if none."
    )

    def to_step(self) -> Step:
        return Step(
            id=self.id,
            latex=self.latex,
            sympy=self.sympy,
            kind=self.kind,
            relation=self.relation,
            derives_from=self.derives_from,
            confidence=self.confidence,
            legible=self.legible,
            notes=self.notes,
        )


class RecognitionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[RecognizedStep] = Field(
        description="Every step visible in the image, in reading order. Never invent "
        "a step that is not there."
    )


class HintPayload(BaseModel):
    """What the model fills in for a level-1 hint. Flat and without defaults,
    like the recognition schema: every field is a decision the model must make."""

    model_config = ConfigDict(extra="forbid")

    step_id: str | None = Field(
        description="Id of the step that fails, or null if you see no mistake."
    )
    error_type: str | None = Field(
        description="Id of the error type from the list in the instructions, or null "
        "if none fits or there is no mistake."
    )
    hint: str = Field(
        description="The hint, in Spanish. Never the corrected step or the final answer. "
        "Empty if there is no mistake."
    )


class NotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(description="Id of the step this comment is about.")
    note: str = Field(description="One or two sentences, in Spanish.")


class ExplanationPayload(BaseModel):
    """What the model fills in for a level-2 explanation."""

    model_config = ConfigDict(extra="forbid")

    overview: str = Field(
        description="What kind of problem this is, which method applies and why. Spanish."
    )
    notes: list[NotePayload] = Field(
        description="One comment per step that deserves one: the rule it applies and why "
        "it is valid, or, for the failing step, the mistake and the idea behind it."
    )
    suspect_step_id: str | None = Field(
        description="Only when the verifier found no error: id of an unverifiable step you "
        "believe is wrong, or null."
    )
    corrected_latex: str | None = Field(
        description="How the failing step should have been written, KaTeX-compatible, or "
        "null if no step fails."
    )
    corrected_sympy: str | None = Field(
        description="The corrected step in the SymPy dialect, or null."
    )
    next_step: str = Field(
        description="If the development stops before the result: what to do next, without "
        "doing it. Empty if it is finished."
    )
    takeaway: str = Field(description="One sentence worth remembering. Spanish.")


class SolvedStep(BaseModel):
    """One step of the model's own solution. Same shape as a transcribed step,
    minus what only applies to reading handwriting."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="r1, r2, r3...")
    latex: str = Field(description="The step, KaTeX-compatible.")
    sympy: str | None = Field(
        description="The step in the SymPy dialect, or null for a step in words."
    )
    kind: StepKind
    relation: StepRelation
    derives_from: list[str] = Field(
        description="Ids of the steps this one comes from: the given ids (g1...) or "
        "earlier steps of yours."
    )
    why: str = Field(description="Why this step: the rule and why it applies. Spanish.")


class SolutionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(description="What is being asked, in one sentence. Spanish.")
    method: str = Field(description="Which method you use and why it applies. Spanish.")
    steps: list[SolvedStep] = Field(
        description="The solution from the given data to the result, one step per line."
    )
    answer: str = Field(description="The final result, with LaTeX between $...$.")
    check: str = Field(
        description="How to check the result: substitute it, check units or a limit case."
    )
