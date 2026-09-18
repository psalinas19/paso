"""Recognition: image + subject -> steps (SPEC 6.2).

A pure function over the schema types, with the provider injected. Phase 2
wraps this in POST /api/recognize without changing it (ADR 0001).
"""

from __future__ import annotations

from pathlib import Path

from app.config import PROMPTS_DIR, Settings, get_settings
from app.llm.base import LLMProvider, PromptSpec
from app.llm.usage import record as record_usage
from app.recognition import cache
from app.recognition.image import prepare_image
from app.schemas import RecognitionResult, Step, StepRelation
from app.subjects.loader import SubjectConfig

RECOGNIZE_PROMPT = PROMPTS_DIR / "recognize.system.md"

INSTRUCTION = (
    "Transcribe el desarrollo de esta imagen paso por paso, siguiendo exactamente "
    "las reglas del sistema. No lo resuelvas ni lo corrijas."
)


def build_prompt(subject: SubjectConfig) -> PromptSpec:
    notation_line = f" — notación de {subject.notation}" if subject.notation else ""
    return PromptSpec.from_file(
        RECOGNIZE_PROMPT,
        subject_name=subject.name,
        notation_line=notation_line,
        notation_notes=subject.notation_notes.strip() or "(sin notas específicas)",
    )


def repair_steps(steps: list[Step]) -> tuple[list[Step], list[str]]:
    """Fix what the model can plausibly get wrong about step wiring.

    Repairing rather than rejecting: a dangling reference should not throw away
    a whole page that was otherwise read correctly. Every repair is recorded so
    the eval can count them instead of them passing unnoticed.
    """
    warnings: list[str] = []
    known: set[str] = set()
    repaired: list[Step] = []

    for step in steps:
        dangling = [pid for pid in step.derives_from if pid not in known]
        if dangling:
            warnings.append(
                f"{step.id}: ignoré referencias a pasos inexistentes o posteriores "
                f"({', '.join(dangling)})."
            )
            step = step.model_copy(
                update={"derives_from": [p for p in step.derives_from if p in known]}
            )

        if step.relation is StepRelation.GIVEN and step.derives_from:
            warnings.append(f"{step.id}: es un dato, así que ignoré su derives_from.")
            step = step.model_copy(update={"derives_from": []})

        # A step that claims to come from somewhere but names nowhere is wired
        # to the previous step, which is the overwhelmingly common case.
        needs_parent = step.relation not in (StepRelation.GIVEN, StepRelation.ASSERTION)
        if needs_parent and not step.derives_from and repaired:
            previous = repaired[-1].id
            warnings.append(f"{step.id}: no dijo de qué paso proviene; lo enlacé con {previous}.")
            step = step.model_copy(update={"derives_from": [previous]})

        known.add(step.id)
        repaired.append(step)

    return repaired, warnings


def recognize(
    image_path: Path,
    subject: SubjectConfig,
    provider: LLMProvider,
    settings: Settings | None = None,
    use_cache: bool | None = None,
    cache_only: bool = False,
) -> RecognitionResult:
    """Read one image. Returns the transcription plus its provenance.

    With `cache_only`, never calls the API: used by `app.eval --no-llm` to
    re-run the verifier over previously recognised images for free.
    """
    settings = settings or get_settings()
    use_cache = settings.recognition_cache_enabled if use_cache is None else use_cache

    image = prepare_image(image_path, settings.max_image_edge)
    prompt = build_prompt(subject)
    key = cache.cache_key(image.sha256, prompt.version, provider.model, subject.slug)

    if use_cache or cache_only:
        cached = cache.load(key)
        if cached is not None:
            if cached.usage:
                cached.usage.cache_hit = True
            return cached

    if cache_only:
        raise LookupError(
            f"No hay reconocimiento en caché para {image_path.name} con el prompt "
            f"{prompt.version} y el modelo {provider.model}. Corre el eval sin "
            "--no-llm al menos una vez."
        )

    result_from_provider = provider.extract_steps(image, prompt, INSTRUCTION)
    steps, repair_warnings = repair_steps(result_from_provider.steps)

    result = RecognitionResult(
        subject=subject.slug,
        steps=steps,
        image=image.to_meta(),
        model=provider.model,
        prompt_version=prompt.version,
        warnings=result_from_provider.warnings + repair_warnings,
        usage=result_from_provider.usage,
    )

    record_usage(
        result.usage,
        subject=subject.slug,
        prompt_version=prompt.version,
        image=image_path.name,
    )
    if use_cache:
        cache.store(key, result)

    return result
