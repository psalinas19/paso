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
