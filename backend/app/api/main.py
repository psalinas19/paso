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
import time
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import UnidentifiedImageError
from pydantic import BaseModel
from sqlmodel import Session, func, select

from app.cli_common import MissingApiKeyError, build_provider
from app.config import Settings, get_settings
from app.db import (
    Check,
    UsageLog,
    current_steps,
    dump_steps,
    make_engine,
    migrate,
    month_spend,
    month_start,
)
from app.llm.base import LLMProvider, ProviderError
from app.recognition.image import prepare_image
from app.recognition.service import recognize
from app.schemas import (
    Explanation,
    Hint,
    RecognitionResult,
    Solution,
    Step,
    StepKind,
    StepRelation,
    Usage,
    VerificationResult,
)
from app.subjects.loader import SubjectConfig, SubjectNotFoundError, load_subject_cached
from app.tutor.correction import MAX_LATEX_CHARS, UnknownStepError, correct_step
from app.tutor.explain import build_explanation
from app.tutor.hint import build_hint
from app.tutor.solve import NothingToSolveError, build_solution
from app.verification.runner import verify, verify_recognition
from app.verification.worker import TimeoutWorker

#: What the notebook may ask for in its "speed" setting. The slower, more
#: thorough levels stay a deliberate choice in .env, not a tap in the app.
EFFORTS = frozenset({"low", "medium", "high"})

#: A selection is a PNG of pen strokes on white; a few hundred KB is typical.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


class UsageSummary(BaseModel):
    month_spend_usd: float
    budget_usd: float
    checks_this_month: int


class CheckResponse(BaseModel):
    """A review as it stands now. Every endpoint that changes one returns this."""

    id: str
    #: The steps are the current ones: as read, with the student's corrections applied.
    recognition: RecognitionResult
    verification: VerificationResult
    #: Ids of the steps the student retyped.
    corrected: list[str] = []
    hint: Hint | None = None
    explanation: Explanation | None = None
    solution: Solution | None = None
    #: What this call cost, not the review's running total.
    cost_usd: float
    #: Where this call's time went, in seconds: waiting for the model, and
    #: checking the steps. The rest of what the user waited is network.
    model_seconds: float = 0.0
    verify_seconds: float = 0.0
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

    def refuse_over_budget(db: Session) -> None:
        # Refuse before spending: once the month's budget is used up, no call is made.
        spent = month_spend(db)
        if spent >= settings.monthly_budget_usd:
            raise HTTPException(
                402,
                f"Se alcanzó el límite mensual de gasto ({spent:.2f} de "
                f"{settings.monthly_budget_usd:.2f} USD). Súbelo en MONTHLY_BUDGET_USD "
                "o espera al mes siguiente.",
            )

    # One client per effort level, kept for the life of the server: building a
    # new one for every request also opened a new connection every time.
    providers: dict[str | None, LLMProvider] = {}

    def model(effort: str | None = None) -> LLMProvider:
        if effort is not None and effort not in EFFORTS:
            raise HTTPException(422, "La velocidad pedida no existe. Usa low, medium o high.")
        if provider is not None:
            return provider
        if effort not in providers:
            try:
                providers[effort] = build_provider(settings, effort)
            except MissingApiKeyError as exc:
                raise HTTPException(503, str(exc)) from exc
        return providers[effort]

    def charge(db: Session, endpoint: str, usage: Usage | None) -> float:
        """Record one paid call; returns its cost."""
        if usage is None or usage.cache_hit:
            return 0.0
        db.add(
            UsageLog(
                endpoint=endpoint,
                model=usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=usage.cost_usd,
            )
        )
        return usage.cost_usd

    def stored(db: Session, check_id: str) -> tuple[Check, SubjectConfig]:
        found = db.get(Check, check_id)
        if found is None:
            raise HTTPException(404, "No existe esa revisión en el backend.")
        try:
            return found, load_subject_cached(found.subject)
        except SubjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    def respond(
        db: Session,
        row: Check,
        cost: float,
        model_ms: float = 0.0,
        verify_seconds: float = 0.0,
    ) -> CheckResponse:
        steps, corrected = current_steps(row)
        recognition = RecognitionResult.model_validate_json(row.steps_json)
        return CheckResponse(
            id=row.id,
            recognition=recognition.model_copy(update={"steps": steps}),
            verification=VerificationResult.model_validate_json(row.verification_json),
            corrected=corrected,
            hint=Hint.model_validate_json(row.hint_json) if row.hint_json else None,
            explanation=(
                Explanation.model_validate_json(row.explanation_json)
                if row.explanation_json
                else None
            ),
            solution=Solution.model_validate_json(row.solution_json) if row.solution_json else None,
            cost_usd=round(cost, 4),
            model_seconds=round(model_ms / 1000, 2),
            verify_seconds=round(verify_seconds, 2),
            usage=summary(db),
        )

    @app.post("/api/check", dependencies=auth)
    def check(
        db: Db,
        image: UploadFile,
        subject: Annotated[str, Form()],
        strokes: Annotated[str | None, Form()] = None,
        effort: Annotated[str | None, Form()] = None,
    ) -> CheckResponse:
        try:
            subject_config = load_subject_cached(subject)
        except SubjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

        refuse_over_budget(db)

        data = image.file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "La imagen es demasiado grande. Selecciona una región menor.")

        llm = model(effort)

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

        started = time.perf_counter()
        with worker_lock:
            verification = verify_recognition(subject_config, recognition, worker=worker)
        verifying = time.perf_counter() - started

        cost = charge(db, "check", recognition.usage)
        row = Check(
            id=check_id,
            subject=subject_config.slug,
            image_path=str(path),
            strokes_json=strokes,
            steps_json=recognition.model_dump_json(),
            verification_json=verification.model_dump_json(),
            model=recognition.model,
            prompt_version=recognition.prompt_version,
        )
        db.add(row)
        db.commit()
        reading = recognition.usage.latency_ms if recognition.usage and cost else 0
        return respond(db, row, cost, reading, verifying)

    @app.post("/api/checks/{check_id}/steps/{step_id}", dependencies=auth)
    def correct(
        db: Db,
        check_id: str,
        step_id: str,
        latex: Annotated[str, Form()],
        effort: Annotated[str | None, Form()] = None,
    ) -> CheckResponse:
        """The student retyped a misread step: restructure it and verify again."""
        row, subject_config = stored(db, check_id)
        steps, _ = current_steps(row)
        current = next((s for s in steps if s.id == step_id), None)
        if current is None:
            raise HTTPException(404, f"La revisión no tiene un paso '{step_id}'.")
        latex = latex.strip()
        if not latex:
            raise HTTPException(422, "Escribe el paso antes de guardarlo.")
        if len(latex) > MAX_LATEX_CHARS:
            raise HTTPException(422, "El paso es demasiado largo. Corrige un renglón a la vez.")
        if latex == current.latex.strip():
            # Nothing changed: nothing to pay for. But saving a doubtful reading
            # as it stands is the student saying "yes, that is what I wrote".
            if current.is_low_confidence:
                confirmed = [
                    s.model_copy(update={"confidence": 1.0}) if s.id == step_id else s
                    for s in steps
                ]
                row.corrected_steps_json = dump_steps(confirmed)
                db.add(row)
                db.commit()
            return respond(db, row, 0.0)

        refuse_over_budget(db)
        try:
            updated, usage, _ = correct_step(subject_config, steps, step_id, latex, model(effort))
        except UnknownStepError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc

        started = time.perf_counter()
        with worker_lock:
            verification = verify(subject_config, updated, worker=worker)
        verifying = time.perf_counter() - started

        cost = charge(db, "correct", usage)
        row.corrected_steps_json = dump_steps(updated)
        row.verification_json = verification.model_dump_json()
        # Written for the old reading; none of it applies any more.
        row.hint_json = row.explanation_json = row.solution_json = None
        db.add(row)
        db.commit()
        return respond(db, row, cost, usage.latency_ms, verifying)

    @app.post("/api/checks/{check_id}/hint", dependencies=auth)
    def hint(db: Db, check_id: str, effort: Annotated[str | None, Form()] = None) -> CheckResponse:
        """Level 1 (SPEC 2.5): which step fails and a nudge, without the answer."""
        row, subject_config = stored(db, check_id)
        if row.hint_json:
            return respond(db, row, 0.0)  # already paid for; a correction clears it

        refuse_over_budget(db)
        steps, _ = current_steps(row)
        verification = VerificationResult.model_validate_json(row.verification_json)
        try:
            picture = prepare_image(Path(row.image_path), settings.max_image_edge)
        except (OSError, UnidentifiedImageError):
            picture = None  # the hint still works from the transcription alone
        try:
            result, usage = build_hint(subject_config, steps, verification, model(effort), picture)
        except ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc

        cost = charge(db, "hint", usage)
        row.hint_json = result.model_dump_json()
        db.add(row)
        db.commit()
        return respond(db, row, cost, usage.latency_ms if usage else 0)

    def picture_of(row: Check):
        try:
            return prepare_image(Path(row.image_path), settings.max_image_edge)
        except (OSError, UnidentifiedImageError):
            return None  # the tutor still works from the transcription alone

    def verifier_for(subject_config: SubjectConfig, spent: list[float]):
        """The verifier as the tutor calls it; `spent` collects how long it took."""

        def run(steps: list[Step]) -> VerificationResult:
            started = time.perf_counter()
            with worker_lock:
                result = verify(subject_config, steps, worker=worker)
            spent.append(time.perf_counter() - started)
            return result

        return run

    @app.post("/api/checks/{check_id}/level/2", dependencies=auth)
    def explain(
        db: Db, check_id: str, effort: Annotated[str | None, Form()] = None
    ) -> CheckResponse:
        """Level 2 (SPEC 2.5): why each step holds, what went wrong and the corrected step."""
        row, subject_config = stored(db, check_id)
        if row.explanation_json:
            return respond(db, row, 0.0)  # already paid for; a correction clears it

        refuse_over_budget(db)
        steps, _ = current_steps(row)
        verification = VerificationResult.model_validate_json(row.verification_json)
        spent: list[float] = []
        try:
            result, usage = build_explanation(
                subject_config,
                steps,
                verification,
                model(effort),
                verifier_for(subject_config, spent),
                picture_of(row),
            )
        except ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc

        cost = charge(db, "explain", usage)
        row.explanation_json = result.model_dump_json()
        row.max_level_shown = max(row.max_level_shown, 2)
        db.add(row)
        db.commit()
        return respond(db, row, cost, usage.latency_ms, sum(spent))

    @app.post("/api/checks/{check_id}/solve", dependencies=auth)
    def solve(db: Db, check_id: str, effort: Annotated[str | None, Form()] = None) -> CheckResponse:
        """Level 3 (SPEC 6.4): the worked solution, verified before it is shown."""
        row, subject_config = stored(db, check_id)
        if row.solution_json:
            return respond(db, row, 0.0)

        refuse_over_budget(db)
        steps, _ = current_steps(row)
        verification = VerificationResult.model_validate_json(row.verification_json)
        spent = []
        try:
            result, usages = build_solution(
                subject_config,
                steps,
                verification,
                model(effort),
                verifier_for(subject_config, spent),
                picture_of(row),
            )
        except NothingToSolveError as exc:
            raise HTTPException(422, str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc

        cost = sum(charge(db, "solve", usage) for usage in usages)
        row.solution_json = result.model_dump_json()
        row.max_level_shown = 3
        db.add(row)
        db.commit()
        return respond(db, row, cost, sum(u.latency_ms for u in usages), sum(spent))

    return app


def _app() -> FastAPI:
    return create_app()


# `uvicorn app.api.main:app` -- built lazily so importing this module (tests,
# tooling) does not touch the real database.
def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return _app()
    raise AttributeError(name)
