"""Shared CLI pieces: provider construction and result rendering."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text

from app.config import Settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.schemas import RecognitionResult, Step, VerificationResult, VerificationStatus

STATUS_MARK = {
    VerificationStatus.CORRECT: ("[OK]", "green"),
    VerificationStatus.ERROR: ("[X]", "red"),
    VerificationStatus.UNVERIFIABLE: ("[?]", "yellow"),
}


class MissingApiKeyError(RuntimeError):
    pass


def build_provider(settings: Settings, effort: str | None = None) -> LLMProvider:
    """`effort` overrides ANTHROPIC_EFFORT for this provider; None keeps the setting."""
    if not settings.anthropic_api_key:
        raise MissingApiKeyError(
            "Falta ANTHROPIC_API_KEY. Copia backend/.env.example a backend/.env y "
            "pon tu clave, o inicia sesión con `ant auth login`."
        )
    return AnthropicProvider(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
        effort=(effort or settings.anthropic_effort).strip().lower() or None,
        chat_model=settings.anthropic_model_chat.strip() or None,
    )


def _short(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_steps(
    console: Console,
    recognition: RecognitionResult,
    verification: VerificationResult,
) -> None:
    verdicts = verification.by_id()
    table = Table(show_lines=False, header_style="bold")
    table.add_column("", width=4)
    table.add_column("Paso", width=5)
    table.add_column("Transcripción", overflow="fold")
    table.add_column("Relación", width=15)
    table.add_column("Conf.", width=6, justify="right")
    table.add_column("Qué dice el verificador", overflow="fold")

    for step in recognition.steps:
        verdict = verdicts.get(step.id)
        mark, colour = STATUS_MARK.get(
            verdict.status if verdict else VerificationStatus.UNVERIFIABLE, ("[?]", "yellow")
        )
        confidence = Text(
            f"{step.confidence:.2f}", style="yellow" if step.is_low_confidence else ""
        )
        parents = f" <- {','.join(step.derives_from)}" if step.derives_from else ""
        detail = verdict.detail if verdict else ""
        if verdict and verdict.depends_on_error:
            detail = f"{detail}"

        table.add_row(
            Text(mark, style=colour),
            step.id,
            _short(step.sympy or step.latex, 70),
            f"{step.relation.value}{parents}",
            confidence,
            _short(detail, 80),
        )

    console.print(table)


def render_summary(
    console: Console,
    recognition: RecognitionResult,
    verification: VerificationResult,
) -> None:
    counts = {status: verification.count(status) for status in VerificationStatus}
    console.print(
        f"\n[green]{counts[VerificationStatus.CORRECT]} correctos[/green]  "
        f"[red]{counts[VerificationStatus.ERROR]} con error[/red]  "
        f"[yellow]{counts[VerificationStatus.UNVERIFIABLE]} no verificables[/yellow]"
    )

    low = [s.id for s in recognition.steps if s.is_low_confidence]
    if low:
        console.print(
            f"[yellow]Confianza baja en: {', '.join(low)}. "
            "Revisa que la transcripción sea correcta antes de fiarte.[/yellow]"
        )

    for warning in recognition.warnings:
        console.print(f"[yellow]aviso:[/yellow] {warning}")

    if recognition.usage:
        usage = recognition.usage
        origin = "desde caché, sin costo" if usage.cache_hit else f"${usage.cost_usd:.4f}"
        console.print(
            f"\n[dim]modelo {recognition.model} · prompt {recognition.prompt_version} · "
            f"{usage.input_tokens} tokens entrada, {usage.output_tokens} salida · "
            f"{origin} · {usage.latency_ms} ms[/dim]"
        )


def first_error(recognition: RecognitionResult, verification: VerificationResult) -> Step | None:
    verdict = verification.first_error
    if verdict is None:
        return None
    return recognition.by_id().get(verdict.step_id)
