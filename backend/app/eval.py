"""Run the permanent test bank and report the metrics of ADR 0004.

    python -m app.eval              # full run, uses the recognition cache
    python -m app.eval --no-llm     # cache only, costs nothing
    python -m app.eval --case ed-01 # one case

Results are written to eval/results/<timestamp>.json plus a Markdown summary,
and both are committed: they are the record that makes SPEC 12.4 enforceable
("if the score drops, don't change the model").
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from app.cli_common import MissingApiKeyError, build_provider
from app.config import EVAL_RESULTS_DIR, get_settings
from app.evaluation.cases import EvalCase, MalformedCaseError, load_cases, pending_cases
from app.evaluation.scoring import CaseScore, EvalSummary, score_case, summarise
from app.llm.base import LLMProvider, ProviderError
from app.recognition.service import recognize
from app.subjects.loader import SubjectNotFoundError, load_subject
from app.verification.runner import verify

# Targets from ADR 0004. The last two are the ones that matter.
TARGETS = {
    "transcription_accuracy": 0.80,
    "seeded_recall": 1.00,
    "false_error_rate": 0.00,
    "unverifiable_rate": 0.30,
}


class NoProvider:
    """Stands in for a provider when running --no-llm, so nothing can call out."""

    name = "cache-only"

    def __init__(self, model: str) -> None:
        self.model = model

    def extract_steps(self, image, system_prompt, instruction):  # noqa: ANN001
        raise ProviderError("modo --no-llm: no se permiten llamadas al API")


def run_case(
    case: EvalCase,
    provider: LLMProvider,
    settings,  # noqa: ANN001
    cache_only: bool,
    use_cache: bool,
) -> CaseScore | None:
    subject = load_subject(case.meta.subject)

    recognition = recognize(
        case.image_path,
        subject,
        provider,
        settings=settings,
        use_cache=use_cache,
        cache_only=cache_only,
    )
    verification = verify(
        subject, recognition.steps, timeout_seconds=settings.verify_timeout_seconds
    )

    score = score_case(case, recognition.steps, verification, subject)
    score.warnings = list(recognition.warnings)
    if recognition.usage:
        score.cost_usd = 0.0 if recognition.usage.cache_hit else recognition.usage.cost_usd
        score.latency_ms = recognition.usage.latency_ms
        score.cache_hit = recognition.usage.cache_hit
    return score


def render(console: Console, scores: list[CaseScore], summary: EvalSummary) -> None:
    per_case = Table(title="Por caso", header_style="bold")
    per_case.add_column("Caso")
    per_case.add_column("Materia")
    per_case.add_column("Transcripción", justify="right")
    per_case.add_column("Limpia", justify="center")
    per_case.add_column("Sembrados", justify="right")
    per_case.add_column("Falsos X", justify="right")
    per_case.add_column("No verif.", justify="right")

    for score in scores:
        false_style = "red bold" if score.false_errors else "green"
        per_case.add_row(
            score.case_id,
            score.subject,
            f"{score.transcription_accuracy:.0%} ({score.matched_steps}/{score.truth_steps})",
            "sí" if score.is_clean else "no",
            f"{score.seeded_detected}/{score.seeded_verifiable}"
            if score.seeded_verifiable
            else "-",
            f"[{false_style}]{score.false_errors}[/{false_style}]",
            f"{score.unverifiable_steps}/{score.scoreable_steps}",
        )
    console.print(per_case)

    def verdict(ok: bool) -> str:
        return "[green]cumple[/green]" if ok else "[red]NO cumple[/red]"

    totals = Table(title="Criterios de aceptación (ADR 0004)", header_style="bold")
    totals.add_column("Métrica")
    totals.add_column("Resultado", justify="right")
    totals.add_column("Objetivo", justify="right")
    totals.add_column("")

    accuracy_ok = summary.transcription_accuracy >= TARGETS["transcription_accuracy"]
    totals.add_row(
        "Exactitud de transcripción (por paso)",
        f"{summary.transcription_accuracy:.1%}",
        "≥ 80%",
        verdict(accuracy_ok),
    )
    clean_ok = summary.clean_cases >= 8 if summary.cases >= 10 else True
    totals.add_row(
        "Fotos limpias",
        f"{summary.clean_cases}/{summary.cases}",
        "≥ 8 de 10",
        verdict(clean_ok),
    )
    recall_ok = summary.seeded_recall >= TARGETS["seeded_recall"]
    totals.add_row(
        "Errores sembrados detectados",
        f"{summary.seeded_detected}/{summary.seeded_verifiable}"
        if summary.seeded_verifiable
        else "sin datos",
        "100%",
        verdict(recall_ok),
    )
    false_ok = summary.false_errors == 0
    totals.add_row(
        "Falsos errores en pasos correctos",
        f"{summary.false_errors}/{summary.correct_verifiable_steps}",
        "0",
        verdict(false_ok),
    )
    unver_ok = summary.unverifiable_rate <= TARGETS["unverifiable_rate"]
    totals.add_row(
        "Pasos no verificables",
        f"{summary.unverifiable_rate:.1%}",
        "≤ 30%",
        verdict(unver_ok),
    )
    totals.add_row("Exactitud de `relation`", f"{summary.relation_accuracy:.1%}", "-", "")
    console.print(totals)

    if summary.seeded_unverifiable_by_design:
        console.print(
            f"[dim]{summary.seeded_unverifiable_by_design} errores sembrados quedan "
            "fuera del alcance del verificador simbólico por diseño (LCK mal "
            "planteada y similares); solo el modelo puede señalarlos.[/dim]"
        )

    console.print(
        f"\n[dim]costo total ${summary.total_cost_usd:.4f} · "
        f"{summary.total_latency_ms / 1000:.1f} s de latencia acumulada[/dim]"
    )

    problems = [note for score in scores for note in score.notes]
    if problems:
        console.print("\n[bold]Qué revisar:[/bold]")
        for note in problems:
            style = "red" if "FALSO ERROR" in note else "yellow"
            console.print(f"  [{style}]·[/{style}] {note}")


def write_results(
    scores: list[CaseScore], summary: EvalSummary, model: str, results_dir: Path
) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    payload = {
        "timestamp": stamp,
        "model": model,
        "summary": {
            **summary.model_dump(mode="json"),
            "transcription_accuracy": summary.transcription_accuracy,
            "relation_accuracy": summary.relation_accuracy,
            "seeded_recall": summary.seeded_recall,
            "false_error_rate": summary.false_error_rate,
            "unverifiable_rate": summary.unverifiable_rate,
        },
        "cases": [score.model_dump(mode="json") for score in scores],
    }
    json_path = results_dir / f"{stamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Eval {stamp}",
        "",
        f"Modelo: `{model}` · {summary.cases} casos · {summary.truth_steps} pasos",
        "",
        "| Métrica | Resultado | Objetivo |",
        "|---|---|---|",
        f"| Exactitud de transcripción | {summary.transcription_accuracy:.1%} | ≥ 80% |",
        f"| Fotos limpias | {summary.clean_cases}/{summary.cases} | ≥ 8 de 10 |",
        f"| Errores sembrados detectados | {summary.seeded_detected}"
        f"/{summary.seeded_verifiable} | 100% |",
        f"| **Falsos errores** | **{summary.false_errors}** | **0** |",
        f"| Pasos no verificables | {summary.unverifiable_rate:.1%} | ≤ 30% |",
        f"| Exactitud de `relation` | {summary.relation_accuracy:.1%} | - |",
        "",
        f"Costo total: ${summary.total_cost_usd:.4f}",
    ]
    (results_dir / f"{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.eval",
        description="Corre el banco de pruebas y reporta las métricas de ADR 0004.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Usa solo la caché de reconocimiento. No cuesta nada.",
    )
    parser.add_argument("--case", help="Corre un solo caso por id.")
    parser.add_argument("--cases-dir", type=Path, default=None, help="Banco alternativo de casos.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()
    settings = get_settings()

    try:
        cases = load_cases(args.cases_dir)
    except MalformedCaseError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    pending = pending_cases(args.cases_dir)
    if pending:
        console.print(
            f"[yellow]{len(pending)} caso(s) en borrador no se miden: {', '.join(pending)}. "
            "Revísalos y confírmalos con `python -m app.case confirm <id>`.[/yellow]"
        )

    if args.case:
        cases = [c for c in cases if c.id == args.case]

    if not cases:
        console.print(
            "[yellow]No hay casos en el banco de pruebas.[/yellow]\n"
            "Crea backend/eval/cases/<id>/ con image.jpg, meta.yaml y truth.json. "
            "Ver docs/decisions/0004-eval-metrics.md."
        )
        return 1

    if args.no_llm:
        provider: LLMProvider = NoProvider(settings.anthropic_model)
    else:
        try:
            provider = build_provider(settings)
        except MissingApiKeyError as exc:
            console.print(f"[red]{exc}[/red]")
            return 2

    scores: list[CaseScore] = []
    failed = 0
    for case in cases:
        console.print(f"[dim]{case.id}...[/dim]")
        try:
            score = run_case(case, provider, settings, cache_only=args.no_llm, use_cache=True)
        except (ProviderError, LookupError, SubjectNotFoundError, FileNotFoundError) as exc:
            console.print(f"  [red]{case.id}: {exc}[/red]")
            failed += 1
            continue
        if score is not None:
            scores.append(score)

    if not scores:
        console.print("[red]Ningún caso se pudo evaluar.[/red]")
        return 1

    summary = summarise(scores)
    render(console, scores, summary)
    path = write_results(scores, summary, settings.anthropic_model, EVAL_RESULTS_DIR)
    console.print(f"\n[dim]resultados en {path}[/dim]")

    if failed:
        console.print(f"[yellow]{failed} caso(s) no se pudieron evaluar.[/yellow]")

    meets = (
        summary.transcription_accuracy >= TARGETS["transcription_accuracy"]
        and summary.false_errors == 0
        and summary.seeded_recall >= TARGETS["seeded_recall"]
    )
    return 0 if meets and not failed else 1


if __name__ == "__main__":
    sys.exit(main())
