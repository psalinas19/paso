"""The killable-worker path (SPEC 6.3).

These tests actually spawn processes, so they are slower than the rest. They
are worth it: this is the code that keeps a runaway simplify() from hanging the
app, and on Windows it cannot fall back to signal.alarm.
"""

from __future__ import annotations

from app.schemas import StepKind as K
from app.schemas import StepRelation as R
from app.schemas import VerificationStatus
from app.verification.runner import verify
from tests.conftest import mkstep


def _simple_steps():
    return [
        mkstep("s1", "Eq(2*x + 3, 7)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(2*x, 4)", K.EQUATION, R.EQUIVALENT, ("s1",)),
    ]


def test_subprocess_path_agrees_with_in_process(ed):
    in_process = verify(ed, _simple_steps(), timeout_seconds=None)
    subprocess = verify(ed, _simple_steps(), timeout_seconds=30)

    assert [s.status for s in subprocess.steps] == [s.status for s in in_process.steps]
    assert subprocess.by_id()["s2"].status is VerificationStatus.CORRECT


def test_timeout_yields_unverifiable_never_an_error(ed):
    """A step we ran out of time on says nothing about whether it is right, so
    it must never come back as an error (ADR 0004)."""
    result = verify(ed, _simple_steps(), timeout_seconds=0.001)

    for verdict in result.steps:
        assert verdict.status is VerificationStatus.UNVERIFIABLE
        assert verdict.method_used == "timeout"
        assert "tardó más" in verdict.detail


def test_worker_recovers_after_a_timeout(ed):
    """The worker is killed on timeout, so the next step needs a fresh one.
    Without the restart, everything after the first timeout would fail too."""
    steps = [
        mkstep("s1", "Eq(2*x + 3, 7)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(2*x, 4)", K.EQUATION, R.EQUIVALENT, ("s1",)),
        mkstep("s3", "Eq(x, 2)", K.EQUATION, R.EQUIVALENT, ("s2",)),
    ]

    from app.verification.worker import TimeoutWorker

    subject_data = ed.model_dump(mode="json")
    steps_data = [s.model_dump(mode="json") for s in steps]

    with TimeoutWorker(timeout_seconds=0.001) as worker:
        timed_out = worker.verify(subject_data, steps_data, "s2")
        assert timed_out.method_used == "timeout"

        worker.timeout_seconds = 60
        recovered = worker.verify(subject_data, steps_data, "s2")

    assert recovered.status is VerificationStatus.CORRECT
