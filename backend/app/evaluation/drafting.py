"""Turn a stored review into a draft case for the test bank (ADR 0007).

What the model will read in production is a PNG of app ink, so the bank is
built from real reviews instead of notebook photos. The review's transcription
is only a *proposal*: it is written to truth.draft.json, which the eval ignores
until a person has read it against the image, fixed it and confirmed it.
Otherwise the bank would score the model against its own reading.

Pure functions over the schema types; the CLI lives in app/case.py.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.evaluation.cases import (
    DRAFT_NAME,
    IMAGE_NAMES,
    TRUTH_NAME,
    CaseMeta,
    CaseTruth,
    SeededError,
    TruthStep,
)
from app.schemas import Step, VerificationResult, VerificationStatus
from app.subjects.loader import SubjectConfig
from app.verification.runner import verify
from app.verification.safe_parse import try_parse

CASE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

#: Written into a drafted seeded_error so confirming fails until it is filled in.
FILL_IN = "REVISAR"


class DraftError(ValueError):
    """The draft could not be written or confirmed. The message is for the user, in Spanish."""


def draft_truth(steps: list[Step], verification: VerificationResult) -> CaseTruth:
    """The stored reading as a proposed truth.

    `expected_status` is copied from what the verifier said, again as a
    proposal. A step it marked wrong gets a seeded_error stub whose type must
    be filled in by hand: the kind of mistake is a human judgement.
    """
    verdicts = verification.by_id()
    truth_steps = []
    for step in steps:
        verdict = verdicts.get(step.id)
        status = verdict.status if verdict else VerificationStatus.UNVERIFIABLE
        seeded = None
        if status is VerificationStatus.ERROR:
            seeded = SeededError(
                type=FILL_IN,
                verifiable=True,
                note=f"{FILL_IN}: confirma que el error está en la hoja y no en la lectura, "
                "y pon el tipo de error de la materia.",
            )
        truth_steps.append(
            TruthStep(
                id=step.id,
                latex=step.latex,
                sympy=step.sympy if step.legible else None,
                kind=step.kind,
                relation=step.relation,
                derives_from=step.derives_from,
                expected_status=status,
                seeded_error=seeded,
            )
        )
    return CaseTruth(steps=truth_steps)


def write_draft(
    cases_dir: Path,
    case_id: str,
    *,
    subject: str,
    image_path: Path,
    steps: list[Step],
    verification: VerificationResult,
    topic: str = "",
    source: str = "",
    notes: str = "",
) -> Path:
    """Create cases/<case_id>/ with the image, meta.yaml and truth.draft.json."""
    if not CASE_ID.match(case_id):
        raise DraftError(
            f"'{case_id}' no sirve como id de caso. Usa minúsculas, números y guiones: ed-01."
        )
    if not image_path.is_file():
        raise DraftError(f"No encuentro la imagen de la revisión ({image_path}).")
    directory = cases_dir / case_id
    if directory.exists():
        raise DraftError(f"Ya existe el caso '{case_id}'. Elige otro id o borra esa carpeta.")

    doubtful = [s.id for s in steps if s.is_low_confidence or not s.legible]
    if doubtful:
        notes = f"{notes} Pasos de lectura dudosa: {', '.join(doubtful)}.".strip()

    directory.mkdir(parents=True)
    suffix = image_path.suffix.lower() or ".png"
    shutil.copyfile(image_path, directory / f"image{suffix}")
    meta = CaseMeta(id=case_id, subject=subject, topic=topic, source=source, notes=notes)
    (directory / "meta.yaml").write_text(
        yaml.safe_dump(meta.model_dump(), allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    truth = draft_truth(steps, verification)
    (directory / DRAFT_NAME).write_text(
        json.dumps(truth.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return directory


@dataclass
class DraftReview:
    """What confirming a draft found."""

    truth: CaseTruth | None = None
    #: Reasons the draft cannot become a case yet.
    problems: list[str] = field(default_factory=list)
    #: Worth a look, but they do not block: the eval exists to measure exactly these.
    warnings: list[str] = field(default_factory=list)
    #: What the verifier says today about the annotated steps.
    verification: VerificationResult | None = None


def review_draft(directory: Path, subject: SubjectConfig) -> DraftReview:
    """Check a draft the way the eval will use it. Changes nothing on disk."""
    review = DraftReview()
    draft_path = directory / DRAFT_NAME
    if not draft_path.is_file():
        review.problems.append(f"No hay {DRAFT_NAME} en {directory.name}.")
        return review
    if not any((directory / name).is_file() for name in IMAGE_NAMES):
        review.problems.append("Falta la imagen del caso.")

    try:
        truth = CaseTruth.model_validate_json(draft_path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        review.problems.append(
            f"El borrador no tiene el formato esperado ({where}: {first['msg']})."
        )
        return review
    review.truth = truth

    ids = [s.id for s in truth.steps]
    if len(ids) != len(set(ids)):
        review.problems.append("Hay ids de paso repetidos.")
    known_types = {e.id for e in subject.error_types}
    seen: set[str] = set()
    for step in truth.steps:
        missing = [p for p in step.derives_from if p not in seen]
        if missing:
            review.problems.append(
                f"{step.id}: derives_from nombra pasos que no existen antes ({', '.join(missing)})."
            )
        seen.add(step.id)

        if step.sympy:
            _, reason = try_parse(step.sympy, subject)
            if reason:
                review.problems.append(f"{step.id}: el campo sympy no se puede leer ({reason}).")

        seeded = step.seeded_error
        if seeded is not None:
            if seeded.type not in known_types:
                review.problems.append(
                    f"{step.id}: pon en seeded_error.type uno de los tipos de la materia "
                    f"({', '.join(sorted(known_types)) or 'ninguno definido'}), o quita "
                    "seeded_error si el paso está bien."
                )
            if FILL_IN in seeded.note:
                review.problems.append(
                    f"{step.id}: borra la marca {FILL_IN} de la nota al revisarlo."
                )
        elif step.expected_status is VerificationStatus.ERROR:
            review.problems.append(
                f"{step.id}: se espera error pero no tiene seeded_error; sin él no se mide."
            )

    if review.problems:
        return review

    # In-process: annotated steps are our own data, and this is an offline tool.
    result = verify(subject, [s.as_step() for s in truth.steps], timeout_seconds=None)
    review.verification = result
    verdicts = result.by_id()
    for step in truth.steps:
        actual = verdicts[step.id].status
        if actual is step.expected_status:
            continue
        if step.seeded_error is not None and not step.seeded_error.verifiable:
            continue
        if (
            step.expected_status is VerificationStatus.CORRECT
            and actual is VerificationStatus.ERROR
        ):
            review.warnings.append(
                f"{step.id}: lo anotaste como correcto y el verificador lo marca con error "
                f"({verdicts[step.id].detail}). Si la anotación está bien, esto es un falso "
                "error del verificador y el banco lo va a contar."
            )
        else:
            review.warnings.append(
                f"{step.id}: esperabas {step.expected_status.value} y el verificador dice "
                f"{actual.value}."
            )
    return review


def confirm_draft(directory: Path) -> Path:
    """Promote the draft to truth.json. Call only after review_draft found no problems."""
    target = directory / TRUTH_NAME
    if target.exists():
        raise DraftError(f"{directory.name} ya tiene {TRUTH_NAME}.")
    (directory / DRAFT_NAME).rename(target)
    return target
