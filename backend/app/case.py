"""Build test-bank cases from reviews stored by the API (ADR 0007).

    python -m app.case list                       # stored reviews
    python -m app.case new <review> --id ed-01    # draft a case from one
    python -m app.case confirm ed-01              # after reading and fixing the draft

`new` copies the review's image and writes its transcription as
truth.draft.json. The eval ignores the case until `confirm` promotes it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table
from sqlmodel import Session, col, select

from app.cli_common import STATUS_MARK
from app.config import EVAL_CASES_DIR, get_settings
from app.db import Check, current_steps, make_engine, migrate
from app.evaluation.cases import DRAFT_NAME, CaseMeta
from app.evaluation.drafting import DraftError, confirm_draft, review_draft, write_draft
from app.schemas import RecognitionResult, VerificationResult, VerificationStatus
from app.subjects.loader import SubjectNotFoundError, load_subject


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.case",
        description="Convierte revisiones guardadas en casos del banco de pruebas.",
    )
    parser.add_argument("--cases-dir", type=Path, default=None, help="Banco alternativo de casos.")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="Lista las revisiones guardadas, la más reciente primero.")

    show = commands.add_parser(
        "show", help="Imprime una revisión completa, para pegarla al reportar un problema."
    )
    show.add_argument("review", help="Id de la revisión, o sus primeros caracteres.")

    new = commands.add_parser("new", help="Crea el borrador de un caso desde una revisión.")
    new.add_argument("review", help="Id de la revisión, o sus primeros caracteres.")
    new.add_argument("--id", required=True, dest="case_id", help="Id del caso: ed-01.")
    new.add_argument("--topic", default="", help="Tema: variables-separables.")
    new.add_argument("--source", default="", help="De dónde salió el ejercicio.")

    confirm = commands.add_parser("confirm", help="Revisa un borrador y lo mete al banco.")
    confirm.add_argument("case_id", help="Id del caso.")
    return parser


def _find(db: Session, prefix: str) -> Check:
    matches = db.exec(select(Check).where(col(Check.id).startswith(prefix.lower()))).all()
    if not matches:
        raise DraftError(f"No hay ninguna revisión cuyo id empiece con '{prefix}'.")
    if len(matches) > 1:
        raise DraftError(f"'{prefix}' coincide con {len(matches)} revisiones. Escribe más letras.")
    return matches[0]


def cmd_list(console: Console, db: Session) -> int:
    checks = db.exec(select(Check).order_by(col(Check.created_at).desc())).all()
    if not checks:
        console.print("[yellow]Todavía no hay revisiones guardadas.[/yellow]")
        return 1
    table = Table(header_style="bold")
    for name in ("Revisión", "Fecha", "Materia", "Pasos", "Con error", "Corregidos"):
        table.add_column(name)
    for check in checks:
        steps, corrected = current_steps(check)
        verification = VerificationResult.model_validate_json(check.verification_json)
        table.add_row(
            check.id[:8],
            check.created_at.strftime("%Y-%m-%d %H:%M"),
            check.subject,
            str(len(steps)),
            str(verification.count(VerificationStatus.ERROR)),
            str(len(corrected)),
        )
    console.print(table)
    return 0


def cmd_show(db: Session, args: argparse.Namespace) -> int:
    """Everything needed to reproduce what the app said about one review, as
    plain text. No image and nothing personal: only what was read and judged."""
    check = _find(db, args.review)
    steps, corrected = current_steps(check)
    verdicts = VerificationResult.model_validate_json(check.verification_json).by_id()
    lines = [
        f"revisión {check.id[:8]} · materia {check.subject} · modelo {check.model} · "
        f"prompt {check.prompt_version}",
    ]
    for step in steps:
        verdict = verdicts.get(step.id)
        lines.append(
            f"{step.id} | {step.kind.value} | {step.relation.value} | "
            f"sale de: {','.join(step.derives_from) or '-'} | confianza {step.confidence:.2f}"
            f"{' | corregido a mano' if step.id in corrected else ''}"
        )
        lines.append(f"    latex: {step.latex}")
        lines.append(f"    sympy: {step.sympy}")
        if verdict:
            lines.append(f"    -> {verdict.status.value} ({verdict.method_used}): {verdict.detail}")
    for label, stored in (
        ("pista", check.hint_json),
        ("explicación", check.explanation_json),
        ("solución", check.solution_json),
    ):
        if stored:
            lines += ["", f"{label}: {stored}"]
    # Plain print: rich would wrap long lines and eat the brackets of a formula.
    print("\n".join(lines))
    return 0


def cmd_new(console: Console, db: Session, args: argparse.Namespace, cases_dir: Path) -> int:
    check = _find(db, args.review)
    steps, corrected = current_steps(check)
    recognition = RecognitionResult.model_validate_json(check.steps_json)
    notes = (
        f"Borrador generado de la revisión {check.id[:8]} "
        f"(modelo {recognition.model}, prompt {recognition.prompt_version})."
    )
    if corrected:
        notes += f" Pasos corregidos a mano en la app: {', '.join(corrected)}."
    directory = write_draft(
        cases_dir,
        args.case_id,
        subject=check.subject,
        image_path=Path(check.image_path),
        steps=steps,
        verification=VerificationResult.model_validate_json(check.verification_json),
        topic=args.topic,
        source=args.source,
        notes=notes,
    )
    console.print(f"[green]Borrador creado en {directory}[/green]")
    console.print(
        f"\nAún [bold]no cuenta[/bold] en el banco de pruebas. Falta tu parte:\n"
        f"  1. Abre la imagen y {DRAFT_NAME} lado a lado.\n"
        "  2. Corrige cada paso hasta que diga lo que de verdad está escrito "
        "(latex, sympy, relation, derives_from).\n"
        "  3. En los pasos con error, pon el tipo en seeded_error.type y si es "
        "comprobable (verifiable); ver backend/eval/README.md.\n"
        f"  4. Corre: python -m app.case confirm {args.case_id}"
    )
    return 0


def cmd_confirm(console: Console, args: argparse.Namespace, cases_dir: Path) -> int:
    directory = cases_dir / args.case_id
    meta_path = directory / "meta.yaml"
    if not meta_path.is_file():
        raise DraftError(f"No existe el caso '{args.case_id}' en {cases_dir}.")
    meta = CaseMeta.model_validate(yaml.safe_load(meta_path.read_text(encoding="utf-8")))
    try:
        subject = load_subject(meta.subject)
    except SubjectNotFoundError as exc:
        raise DraftError(str(exc)) from exc

    review = review_draft(directory, subject)
    if review.truth and review.verification:
        verdicts = review.verification.by_id()
        table = Table(header_style="bold")
        for name in ("Paso", "Transcripción", "Esperado", "Verificador hoy"):
            table.add_column(name, overflow="fold")
        for step in review.truth.steps:
            mark, colour = STATUS_MARK[verdicts[step.id].status]
            table.add_row(
                step.id,
                step.sympy or step.latex,
                step.expected_status.value,
                f"[{colour}]{mark} {verdicts[step.id].status.value}[/{colour}]",
            )
        console.print(table)
    for warning in review.warnings:
        console.print(f"[yellow]ojo:[/yellow] {warning}")
    if review.problems:
        console.print("[red]El borrador todavía no se puede confirmar:[/red]")
        for problem in review.problems:
            console.print(f"  [red]·[/red] {problem}")
        return 1

    confirm_draft(directory)
    console.print(
        f"[green]{args.case_id} ya es parte del banco de pruebas.[/green] "
        "Agrégalo a git junto con su imagen."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()
    cases_dir = args.cases_dir if args.cases_dir is not None else EVAL_CASES_DIR
    try:
        if args.command == "confirm":
            return cmd_confirm(console, args, cases_dir)
        settings = get_settings()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        migrate(settings.resolved_database_url)
        with Session(make_engine(settings.resolved_database_url)) as db:
            if args.command == "list":
                return cmd_list(console, db)
            if args.command == "show":
                return cmd_show(db, args)
            return cmd_new(console, db, args, cases_dir)
    except DraftError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2


if __name__ == "__main__":
    sys.exit(main())
