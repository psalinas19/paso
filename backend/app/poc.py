"""Phase 0 proof of concept (SPEC 10).

    python -m app.poc foto.jpg --materia ED

Reads one photo, transcribes it and verifies it. No UI, no server, no database.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from app.cli_common import MissingApiKeyError, build_provider, render_steps, render_summary
from app.config import get_settings
from app.llm.base import ProviderError
from app.recognition.service import recognize
from app.subjects.loader import SubjectNotFoundError, available_subjects, load_subject
from app.verification.runner import verify


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.poc",
        description="Transcribe y verifica un desarrollo escrito a mano.",
    )
    parser.add_argument("image", type=Path, help="Foto del desarrollo.")
    parser.add_argument(
        "--materia",
        "--subject",
        dest="subject",
        required=True,
        help=f"Materia. Disponibles: {', '.join(available_subjects()) or 'ninguna'}.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignora la caché y vuelve a pagar el reconocimiento.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Imprime el resultado completo en JSON en vez de la tabla.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()
    settings = get_settings()

    try:
        subject = load_subject(args.subject)
    except SubjectNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    try:
        provider = build_provider(settings)
    except MissingApiKeyError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    console.print(f"[dim]Leyendo {args.image.name} como {subject.name}...[/dim]")

    try:
        recognition = recognize(
            args.image,
            subject,
            provider,
            settings=settings,
            use_cache=not args.no_cache,
        )
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    except ProviderError as exc:
        console.print(f"[red]No se pudo transcribir: {exc}[/red]")
        return 1

    verification = verify(
        subject, recognition.steps, timeout_seconds=settings.verify_timeout_seconds
    )

    if args.json:
        payload = {
            "recognition": recognition.model_dump(mode="json"),
            "verification": verification.model_dump(mode="json"),
        }
        console.print_json(data=payload)
        return 0

    render_steps(console, recognition, verification)
    render_summary(console, recognition, verification)
    return 0


if __name__ == "__main__":
    sys.exit(main())
