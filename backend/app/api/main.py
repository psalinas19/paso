"""HTTP API (SPEC 7): a thin wrapper over recognition and verification.

The endpoints add what a network boundary needs -- a token, a spend limit,
size limits, persistence -- and nothing else. Reading the image and checking
the steps are the same pure functions the CLIs use (ADR 0001).

Run from backend/:
    py -3.12 -m uv run python -m uvicorn app.api.main:app --port 8000
"""

# No "from __future__ import annotations" here: FastAPI resolves the endpoint
# annotations at runtime, and the dependencies below are local to create_app().

import secrets
import threading
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import UnidentifiedImageError
from pydantic import BaseModel
from sqlmodel import Session, func, select

from app.cli_common import MissingApiKeyError, build_provider
from app.config import Settings, get_settings
from app.db import Check, UsageLog, make_engine, migrate, month_spend, month_start
from app.llm.base import LLMProvider, ProviderError
from app.recognition.service import recognize
from app.schemas import RecognitionResult, Step, StepKind, StepRelation, VerificationResult
from app.subjects.loader import SubjectNotFoundError, load_subject_cached
from app.verification.runner import verify, verify_recognition
from app.verification.worker import TimeoutWorker

#: A selection is a PNG of pen strokes on white; a few hundred KB is typical.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


class UsageSummary(BaseModel):
    month_spend_usd: float
    budget_usd: float
    checks_this_month: int


class CheckResponse(BaseModel):
    id: str
    recognition: RecognitionResult
    verification: VerificationResult
    cost_usd: float
    usage: UsageSummary


def create_app(settings: Settings | None = None, provider: LLMProvider | None = None) -> FastAPI:
    """Build the app. Tests pass their own settings and a fake provider."""
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    images_dir = settings.data_dir / "images"
    images_dir.mkdir(exist_ok=True)
    migrate(settings.resolved_database_url)
    engine = make_engine(settings.resolved_database_url)

    # One verification process for the life of the server. Starting it and importing
    # SymPy costs seconds on Windows; paying that on every review would eat a third
    # of the 15 s budget (SPEC 10). The lock keeps its pipe to one request at a time.
    worker = TimeoutWorker(settings.verify_timeout_seconds)
    worker_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # Warm up in the background so the server answers health checks at once.
        def warm() -> None:
            step = Step(
                id="s1",
                latex="x",
                sympy="x",
                kind=StepKind.EXPRESSION,
                relation=StepRelation.GIVEN,
                confidence=1.0,
            )
            with worker_lock:
                verify(load_subject_cached("general"), [step], worker=worker)

        threading.Thread(target=warm, daemon=True).start()
        yield
        worker.close()

    app = FastAPI(title="Paso", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization"],
    )

    def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
        if not settings.app_token:
            raise HTTPException(503, "El backend no tiene APP_TOKEN configurado en backend/.env.")
        sent = (authorization or "").removeprefix("Bearer ").strip()
        # Constant-time comparison: do not leak how much of the token matched.
        if not secrets.compare_digest(sent.encode(), settings.app_token.encode()):
            raise HTTPException(401, "Token incorrecto. Revisa el token en los ajustes de la app.")

    def session() -> Iterator[Session]:
        with Session(engine) as db:
            yield db

    Db = Annotated[Session, Depends(session)]
    auth = [Depends(require_token)]

    def summary(db: Session) -> UsageSummary:
        return UsageSummary(
            month_spend_usd=round(month_spend(db), 4),
            budget_usd=settings.monthly_budget_usd,
            checks_this_month=db.exec(
                select(func.count()).select_from(Check).where(Check.created_at >= month_start())
            ).one(),
        )

    @app.get("/api/health", dependencies=auth)
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/usage", dependencies=auth)
    def usage(db: Db) -> UsageSummary:
        return summary(db)

    @app.post("/api/check", dependencies=auth)
    def check(
        db: Db,
        image: UploadFile,
        subject: Annotated[str, Form()],
        strokes: Annotated[str | None, Form()] = None,
    ) -> CheckResponse:
        try:
            subject_config = load_subject_cached(subject)
        except SubjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

        # Refuse before spending: once the month's budget is used up, no call is made.
        spent = month_spend(db)
        if spent >= settings.monthly_budget_usd:
            raise HTTPException(
                402,
                f"Se alcanzó el límite mensual de gasto ({spent:.2f} de "
                f"{settings.monthly_budget_usd:.2f} USD). Súbelo en MONTHLY_BUDGET_USD "
                "o espera al mes siguiente.",
            )

        data = image.file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "La imagen es demasiado grande. Selecciona una región menor.")

        try:
            llm = provider or build_provider(settings)
        except MissingApiKeyError as exc:
            raise HTTPException(503, str(exc)) from exc

        check_id = uuid.uuid4().hex
        # The name is ours, never the client's: nothing from the request reaches the path.
        path = images_dir / f"{check_id}.png"
        path.write_bytes(data)

        try:
            recognition = recognize(path, subject_config, llm, settings)
        except (UnidentifiedImageError, OSError) as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(400, "El archivo enviado no es una imagen válida.") from exc
        except ProviderError as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(502, str(exc)) from exc

        with worker_lock:
            verification = verify_recognition(subject_config, recognition, worker=worker)

        cost = 0.0
        if recognition.usage and not recognition.usage.cache_hit:
            cost = recognition.usage.cost_usd
            db.add(
                UsageLog(
                    endpoint="check",
                    model=recognition.usage.model,
                    input_tokens=recognition.usage.input_tokens,
                    output_tokens=recognition.usage.output_tokens,
                    cost_usd=cost,
                )
            )
        db.add(
            Check(
                id=check_id,
                subject=subject_config.slug,
                image_path=str(path),
                strokes_json=strokes,
                steps_json=recognition.model_dump_json(),
                verification_json=verification.model_dump_json(),
                model=recognition.model,
                prompt_version=recognition.prompt_version,
            )
        )
        db.commit()

        return CheckResponse(
            id=check_id,
            recognition=recognition,
            verification=verification,
            cost_usd=round(cost, 4),
            usage=summary(db),
        )

    return app


def _app() -> FastAPI:
    return create_app()


# `uvicorn app.api.main:app` -- built lazily so importing this module (tests,
# tooling) does not touch the real database.
def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return _app()
    raise AttributeError(name)
