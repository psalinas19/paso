"""From a stored review to a test-bank case, and the gate in between."""

from __future__ import annotations

import json

import pytest
from PIL import Image
from sqlmodel import Session

from app import case as case_cli
from app.config import Settings
from app.db import Check, dump_steps, make_engine, migrate
from app.eval import main as eval_main
from app.evaluation.cases import DRAFT_NAME, TRUTH_NAME, load_cases, pending_cases
from app.evaluation.drafting import FILL_IN, DraftError, review_draft, write_draft
from app.schemas import RecognitionResult
from app.schemas import StepKind as K
from app.schemas import StepRelation as R
from app.subjects.loader import load_subject
from tests.conftest import mkstep, run

CHECK_ID = "abc123" + "0" * 26


def steps(last="Eq(x, 4)"):
    return [
        mkstep("s1", "Eq(2*x + 4, 10)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(2*x, 6)", K.EQUATION, R.EQUIVALENT, ("s1",), confidence=0.5),
        mkstep("s3", last, K.EQUATION, R.EQUIVALENT, ("s2",)),  # x = 4 is wrong
    ]


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "review.png"
    Image.new("RGB", (300, 120), "white").save(path)
    return path


@pytest.fixture
def bank(tmp_path):
    return tmp_path / "cases"


def draft(bank, image, case_id="gen-01", read=None):
    read = read or steps()
    subject = load_subject("general")
    return write_draft(
        bank,
        case_id,
        subject="general",
        image_path=image,
        steps=read,
        verification=run(subject, read),
    )


def edit(directory, change):
    path = directory / DRAFT_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data["steps"])
    path.write_text(json.dumps(data), encoding="utf-8")


def test_a_draft_copies_the_image_and_proposes_the_reading(bank, image):
    directory = draft(bank, image)

    assert (directory / "image.png").is_file()
    assert not (directory / TRUTH_NAME).exists()
    proposed = json.loads((directory / DRAFT_NAME).read_text(encoding="utf-8"))["steps"]
    assert [s["sympy"] for s in proposed] == ["Eq(2*x + 4, 10)", "Eq(2*x, 6)", "Eq(x, 4)"]
    assert [s["expected_status"] for s in proposed] == ["correct", "correct", "error"]
    # The kind of mistake is a human judgement: the stub has to be filled in.
    assert proposed[2]["seeded_error"]["type"] == FILL_IN
    assert "s2" in (directory / "meta.yaml").read_text(encoding="utf-8")  # doubtful reading


def test_an_unconfirmed_draft_is_never_measured(bank, image, capsys):
    draft(bank, image)

    assert load_cases(bank) == []
    assert pending_cases(bank) == ["gen-01"]
    # The eval says so instead of failing on a folder without truth.json.
    assert eval_main(["--no-llm", "--cases-dir", str(bank)]) == 1
    assert "gen-01" in capsys.readouterr().out


def test_confirming_refuses_a_draft_nobody_reviewed(bank, image):
    directory = draft(bank, image)

    assert case_cli.main(["--cases-dir", str(bank), "confirm", "gen-01"]) == 1
    assert not (directory / TRUTH_NAME).exists()
    problems = review_draft(directory, load_subject("general")).problems
    assert any("seeded_error.type" in p for p in problems)


def test_a_reviewed_draft_becomes_a_case(bank, image):
    directory = draft(bank, image)

    def fill(proposed):
        proposed[2]["seeded_error"] = {"type": "arithmetic", "verifiable": True, "note": ""}

    edit(directory, fill)

    assert case_cli.main(["--cases-dir", str(bank), "confirm", "gen-01"]) == 0
    assert not (directory / DRAFT_NAME).exists()
    [case] = load_cases(bank)
    assert case.id == "gen-01" and len(case.seeded_errors) == 1
    assert pending_cases(bank) == []


def test_confirming_catches_a_truth_that_does_not_parse(bank, image):
    directory = draft(bank, image, read=steps(last="Eq(x, 3)"))
    edit(directory, lambda proposed: proposed[1].update(sympy="Eq(2*x, "))

    review = review_draft(directory, load_subject("general"))
    assert any(p.startswith("s2") and "sympy" in p for p in review.problems)


def test_confirming_warns_when_the_verifier_disagrees_with_the_annotation(bank, image):
    directory = draft(bank, image)
    # The annotator decides s3 was fine after all; the verifier still says error.
    edit(
        directory, lambda proposed: proposed[2].update(expected_status="correct", seeded_error=None)
    )

    review = review_draft(directory, load_subject("general"))
    assert review.problems == []
    assert any("s3" in w and "falso" in w for w in review.warnings)


def test_bad_ids_and_existing_cases_are_refused(bank, image):
    with pytest.raises(DraftError):
        draft(bank, image, case_id="../fuera")
    draft(bank, image)
    with pytest.raises(DraftError):
        draft(bank, image)


def test_the_command_drafts_from_a_stored_review_with_its_corrections(
    bank, image, tmp_path, monkeypatch, capsys
):
    settings = Settings(anthropic_api_key="", app_token="t", data_dir=tmp_path / "data")
    settings.data_dir.mkdir()
    migrate(settings.resolved_database_url)
    monkeypatch.setattr(case_cli, "get_settings", lambda: settings)
    read = steps()
    fixed = steps(last="Eq(x, 3)")
    subject = load_subject("general")
    with Session(make_engine(settings.resolved_database_url)) as db:
        db.add(
            Check(
                id=CHECK_ID,
                subject="general",
                image_path=str(image),
                steps_json=RecognitionResult(
                    subject="general", steps=read, model="fake-model", prompt_version="p1"
                ).model_dump_json(),
                corrected_steps_json=dump_steps(
                    [fixed[0], fixed[1], fixed[2].model_copy(update={"latex": "x = 3"})]
                ),
                verification_json=run(subject, fixed).model_dump_json(),
                model="fake-model",
                prompt_version="p1",
            )
        )
        db.commit()

    assert case_cli.main(["--cases-dir", str(bank), "list"]) == 0
    assert case_cli.main(["--cases-dir", str(bank), "show", "abc123"]) == 0
    assert case_cli.main(["--cases-dir", str(bank), "new", "nope", "--id", "gen-02"]) == 2
    assert case_cli.main(["--cases-dir", str(bank), "new", "abc123", "--id", "gen-02"]) == 0

    proposed = json.loads((bank / "gen-02" / DRAFT_NAME).read_text(encoding="utf-8"))["steps"]
    # The student's correction is the proposal, not the model's misreading.
    assert proposed[2]["sympy"] == "Eq(x, 3)" and proposed[2]["expected_status"] == "correct"
    meta = (bank / "gen-02" / "meta.yaml").read_text(encoding="utf-8")
    assert "abc123" in meta and "s3" in meta
    # `show` prints what was read and judged, whole, for pasting into a report.
    shown = capsys.readouterr().out
    assert "sympy: Eq(x, 3)" in shown and "corregido a mano" in shown and "-> correct" in shown
