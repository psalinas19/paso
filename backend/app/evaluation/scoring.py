"""Eval metrics (ADR 0004).

Transcription is scored by aligning the read steps against the annotated truth
and comparing them *semantically*, not as text: \\frac{1}{2} and 0.5 are the
same reading, and a metric that says otherwise measures formatting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import sympy
from pydantic import BaseModel, ConfigDict, Field

from app.evaluation.cases import EvalCase, TruthStep
from app.schemas import Step, StepRelation, VerificationResult, VerificationStatus
from app.subjects.loader import SubjectConfig
from app.verification.equivalence import Outcome, equation_equivalence, expr_equivalence
from app.verification.safe_parse import try_parse

_LATEX_NOISE = re.compile(r"\\left|\\right|\\,|\\;|\\!|\\ |\s+")


def normalise_latex(text: str) -> str:
    """Strip the differences that are formatting rather than reading."""
    cleaned = _LATEX_NOISE.sub("", text or "")
    return cleaned.replace("\\cdot", "*").replace("\\times", "*").strip()


def steps_match(truth: TruthStep, predicted: Step, subject: SubjectConfig) -> bool:
    """Whether `predicted` is a correct reading of `truth`."""
    truth_parsed, _ = try_parse(truth.sympy, subject)
    pred_parsed, _ = try_parse(predicted.sympy, subject)

    if truth_parsed is not None and pred_parsed is not None:
        if isinstance(truth_parsed, list) or isinstance(pred_parsed, list):
            a = truth_parsed if isinstance(truth_parsed, list) else [truth_parsed]
            b = pred_parsed if isinstance(pred_parsed, list) else [pred_parsed]
            if len(a) != len(b):
                return False
            return all(_expressions_match(x, y, subject) for x, y in zip(a, b, strict=True))
        return _expressions_match(truth_parsed, pred_parsed, subject)

    if truth.sympy is None and predicted.sympy is None:
        return normalise_latex(truth.latex) == normalise_latex(predicted.latex)

    # One side symbolic and the other not: reading an equation as prose is a
    # transcription failure, not a near miss.
    return False


def _expressions_match(a: object, b: object, subject: SubjectConfig) -> bool:
    is_equation = isinstance(a, sympy.Equality) or isinstance(b, sympy.Equality)
    compare = equation_equivalence if is_equation else expr_equivalence
    return compare(a, b, subject).outcome is Outcome.EQUIVALENT


@dataclass
class Alignment:
    """Pairs of (truth index, predicted index); None means unmatched."""

    pairs: list[tuple[int | None, int | None]] = field(default_factory=list)

    @property
    def matched(self) -> list[tuple[int, int]]:
        return [(t, p) for t, p in self.pairs if t is not None and p is not None]

    @property
    def missed(self) -> list[int]:
        """Truth steps with no counterpart: the model did not see them."""
        return [t for t, p in self.pairs if t is not None and p is None]

    @property
    def invented(self) -> list[int]:
        """Read steps with no counterpart in truth."""
        return [p for t, p in self.pairs if t is None and p is not None]


def align(truth: list[TruthStep], predicted: list[Step], subject: SubjectConfig) -> Alignment:
    """Needleman-Wunsch over the two step sequences, matching semantically.

    Alignment rather than zip, because a single missed or invented step would
    otherwise shift everything after it and report a whole page as misread.
    """
    n, m = len(truth), len(predicted)
    gap = -1

    matches = [[steps_match(truth[i], predicted[j], subject) for j in range(m)] for i in range(n)]

    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0] = i * gap
    for j in range(1, m + 1):
        score[0][j] = j * gap

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diagonal = score[i - 1][j - 1] + (1 if matches[i - 1][j - 1] else -1)
            score[i][j] = max(diagonal, score[i - 1][j] + gap, score[i][j - 1] + gap)

    pairs: list[tuple[int | None, int | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            diagonal = score[i - 1][j - 1] + (1 if matches[i - 1][j - 1] else -1)
            if score[i][j] == diagonal:
                # Only count it as a pairing when they actually match; a
                # mismatched diagonal is a misread step, recorded as both a
                # miss and an invention.
                if matches[i - 1][j - 1]:
                    pairs.append((i - 1, j - 1))
                else:
                    pairs.append((i - 1, None))
                    pairs.append((None, j - 1))
                i, j = i - 1, j - 1
                continue
        if i > 0 and score[i][j] == score[i - 1][j] + gap:
            pairs.append((i - 1, None))
            i -= 1
            continue
        pairs.append((None, j - 1))
        j -= 1

    pairs.reverse()
    return Alignment(pairs=pairs)


class CaseScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    subject: str

    truth_steps: int
    read_steps: int
    matched_steps: int
    missed_steps: int
    invented_steps: int
    relation_matches: int

    seeded_verifiable: int = 0
    seeded_detected: int = 0
    seeded_unverifiable_by_design: int = 0

    correct_verifiable_steps: int = 0
    false_errors: int = 0

    unverifiable_steps: int = 0
    scoreable_steps: int = 0

    cost_usd: float = 0.0
    latency_ms: int = 0
    cache_hit: bool = False
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @property
    def transcription_accuracy(self) -> float:
        return self.matched_steps / self.truth_steps if self.truth_steps else 0.0

    @property
    def is_clean(self) -> bool:
        """No missed steps, no invented ones, everything read correctly."""
        return (
            self.missed_steps == 0
            and self.invented_steps == 0
            and self.matched_steps == self.truth_steps
        )


def score_case(
    case: EvalCase,
    predicted: list[Step],
    verification: VerificationResult,
    subject: SubjectConfig,
) -> CaseScore:
    alignment = align(case.truth.steps, predicted, subject)
    verdicts = verification.by_id()

    relation_matches = sum(
        1 for t, p in alignment.matched if case.truth.steps[t].relation is predicted[p].relation
    )

    seeded_verifiable = 0
    seeded_detected = 0
    seeded_by_design = 0
    correct_verifiable = 0
    false_errors = 0
    notes: list[str] = []

    matched_by_truth = {t: p for t, p in alignment.matched}

    for t_index, truth_step in enumerate(case.truth.steps):
        seeded = truth_step.seeded_error
        if seeded is not None and not seeded.verifiable:
            seeded_by_design += 1
            continue

        p_index = matched_by_truth.get(t_index)
        if p_index is None:
            # Not read, so the verifier never got a chance. Counted as a
            # transcription failure above, not held against the verifier.
            continue

        verdict = verdicts.get(predicted[p_index].id)
        if verdict is None:
            continue

        if seeded is not None:
            seeded_verifiable += 1
            if verdict.status is VerificationStatus.ERROR:
                seeded_detected += 1
            else:
                notes.append(
                    f"{truth_step.id}: error sembrado ({seeded.type}) no detectado; "
                    f"salió {verdict.status.value}."
                )
        elif truth_step.expected_status is VerificationStatus.CORRECT:
            correct_verifiable += 1
            if verdict.status is VerificationStatus.ERROR:
                false_errors += 1
                notes.append(
                    f"{truth_step.id}: FALSO ERROR en un paso correcto "
                    f"({verdict.method_used}: {verdict.detail})"
                )

    # Givens are excluded from the warning-rate denominator: reporting one on
    # every piece of problem data would drown the real signal (ADR 0003).
    scoreable = [s for s in predicted if s.relation is not StepRelation.GIVEN]
    unverifiable = sum(
        1
        for s in scoreable
        if verdicts.get(s.id) and verdicts[s.id].status is VerificationStatus.UNVERIFIABLE
    )

    return CaseScore(
        case_id=case.id,
        subject=case.meta.subject,
        truth_steps=len(case.truth.steps),
        read_steps=len(predicted),
        matched_steps=len(alignment.matched),
        missed_steps=len(alignment.missed),
        invented_steps=len(alignment.invented),
        relation_matches=relation_matches,
        seeded_verifiable=seeded_verifiable,
        seeded_detected=seeded_detected,
        seeded_unverifiable_by_design=seeded_by_design,
        correct_verifiable_steps=correct_verifiable,
        false_errors=false_errors,
        unverifiable_steps=unverifiable,
        scoreable_steps=len(scoreable),
        notes=notes,
    )


class EvalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cases: int
    truth_steps: int
    matched_steps: int
    missed_steps: int
    invented_steps: int
    relation_matches: int
    clean_cases: int

    seeded_verifiable: int
    seeded_detected: int
    seeded_unverifiable_by_design: int

    correct_verifiable_steps: int
    false_errors: int

    unverifiable_steps: int
    scoreable_steps: int

    total_cost_usd: float
    total_latency_ms: int

    @property
    def transcription_accuracy(self) -> float:
        return self.matched_steps / self.truth_steps if self.truth_steps else 0.0

    @property
    def relation_accuracy(self) -> float:
        return self.relation_matches / self.matched_steps if self.matched_steps else 0.0

    @property
    def seeded_recall(self) -> float:
        return self.seeded_detected / self.seeded_verifiable if self.seeded_verifiable else 1.0

    @property
    def false_error_rate(self) -> float:
        if not self.correct_verifiable_steps:
            return 0.0
        return self.false_errors / self.correct_verifiable_steps

    @property
    def unverifiable_rate(self) -> float:
        return self.unverifiable_steps / self.scoreable_steps if self.scoreable_steps else 0.0


def summarise(scores: list[CaseScore]) -> EvalSummary:
    def total(attr: str) -> int:
        return sum(getattr(s, attr) for s in scores)

    return EvalSummary(
        cases=len(scores),
        truth_steps=total("truth_steps"),
        matched_steps=total("matched_steps"),
        missed_steps=total("missed_steps"),
        invented_steps=total("invented_steps"),
        relation_matches=total("relation_matches"),
        clean_cases=sum(1 for s in scores if s.is_clean),
        seeded_verifiable=total("seeded_verifiable"),
        seeded_detected=total("seeded_detected"),
        seeded_unverifiable_by_design=total("seeded_unverifiable_by_design"),
        correct_verifiable_steps=total("correct_verifiable_steps"),
        false_errors=total("false_errors"),
        unverifiable_steps=total("unverifiable_steps"),
        scoreable_steps=total("scoreable_steps"),
        total_cost_usd=sum(s.cost_usd for s in scores),
        total_latency_ms=total("latency_ms"),
    )
