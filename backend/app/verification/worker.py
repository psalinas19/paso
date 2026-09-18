"""Per-step timeout for SymPy (SPEC 6.3), portable to Windows.

The usual recipe is signal.alarm, which does not exist on Windows, and a thread
cannot be killed once simplify() runs away with it. So the work happens in a
worker process that can actually be terminated.

The worker is persistent, because spawning a process and importing SymPy costs
about a second on Windows and a page has many steps. It is replaced only when a
step times out, which should be rare.
"""

from __future__ import annotations

import contextlib
import multiprocessing as mp
from multiprocessing.connection import Connection
from typing import Any

from app.schemas import StepVerification, VerificationStatus


def _worker_main(conn: Connection) -> None:  # pragma: no cover - runs in a subprocess
    """Receive (subject, steps, step_id) triples; send back a verification."""
    # Imported inside the child so the parent does not pay for it twice.
    from app.verification.runner import verify_one_in_process

    while True:
        try:
            message = conn.recv()
        except (EOFError, KeyboardInterrupt):
            return
        if message is None:
            return
        subject_data, steps_data, step_id = message
        try:
            result = verify_one_in_process(subject_data, steps_data, step_id)
            conn.send(("ok", result.model_dump(mode="json")))
        except Exception as exc:  # noqa: BLE001 - never let the worker die silently
            conn.send(("error", f"{type(exc).__name__}: {exc}"))


class TimeoutWorker:
    """A restartable subprocess that verifies one step at a time."""

    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self._process: mp.Process | None = None
        self._conn: Connection | None = None

    # --- lifecycle --------------------------------------------------------

    def _start(self) -> None:
        parent_conn, child_conn = mp.Pipe()
        process = mp.Process(target=_worker_main, args=(child_conn,), daemon=True)
        process.start()
        child_conn.close()
        self._process, self._conn = process, parent_conn

    def _restart(self) -> None:
        self.close()
        self._start()

    def close(self) -> None:
        if self._conn is not None:
            # The worker may already be gone; asking it to stop is best effort.
            with contextlib.suppress(BrokenPipeError, OSError):
                self._conn.send(None)
            self._conn.close()
            self._conn = None
        if self._process is not None:
            self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=2.0)
            self._process = None

    def __enter__(self) -> TimeoutWorker:
        self._start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # --- use --------------------------------------------------------------

    def verify(
        self, subject_data: dict[str, Any], steps_data: list[dict[str, Any]], step_id: str
    ) -> StepVerification:
        if self._process is None or not self._process.is_alive() or self._conn is None:
            self._restart()
        assert self._conn is not None

        try:
            self._conn.send((subject_data, steps_data, step_id))
        except (BrokenPipeError, OSError):
            self._restart()
            assert self._conn is not None
            self._conn.send((subject_data, steps_data, step_id))

        if not self._conn.poll(self.timeout_seconds):
            # Still chewing on it. Kill the worker so the runaway computation
            # actually stops, and report the step as unverifiable, never as an
            # error -- a timeout says nothing about whether the step is right.
            self._restart()
            return StepVerification(
                step_id=step_id,
                status=VerificationStatus.UNVERIFIABLE,
                detail=(
                    f"SymPy tardó más de {self.timeout_seconds:g} s en comprobarlo; "
                    "revísalo a mano."
                ),
                method_used="timeout",
            )

        try:
            tag, payload = self._conn.recv()
        except (EOFError, OSError):
            self._restart()
            return StepVerification(
                step_id=step_id,
                status=VerificationStatus.UNVERIFIABLE,
                detail="El verificador se interrumpió al comprobar este paso.",
                method_used="worker-crash",
            )

        if tag == "ok":
            return StepVerification.model_validate(payload)

        return StepVerification(
            step_id=step_id,
            status=VerificationStatus.UNVERIFIABLE,
            detail=f"El verificador falló: {payload}",
            method_used="worker-error",
        )
