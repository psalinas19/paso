"""The HTTP boundary, with the model faked. Never touches the network."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, select

from app.api.main import create_app
from app.config import Settings
from app.db import Check, UsageLog, make_engine
from app.llm.base import ExplanationDraft, HintDraft, ProviderError, ProviderResult, SolutionDraft
from app.schemas import StepKind as K
from app.schemas import StepRelation as R
from app.schemas import Usage
from tests.conftest import mkstep

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self):
        self.calls = 0
        #: What the next correction comes back as: (sympy, derives_from).
        self.rebuilt = ("Eq(x, 3)", ["s2"])
        #: What the model says when asked for a hint: (step_id, error_type, text).
        self.hint = ("s1", "arithmetic", "Revisa la división del paso 3.")
        self.instructions: list[str] = []
        self.hint_images: list[object] = []
        self.fail = False
        #: What the model answers when asked to explain.
        self.explanation = {
            "notes": [("s2", "Restaste 4 en ambos lados."), ("s3", "Dividiste mal."), ("s9", "?")],
            "suspect": None,
            "corrected": ("x = 3", "Eq(x, 3)"),
        }
        #: Successive answers when asked to solve: lists of (id, sympy, relation, parents).
        self.solutions = [
            [
                ("r1", "Eq(2*x, 6)", R.EQUIVALENT, ["g1"]),
                ("r2", "Eq(x, 3)", R.RESULT, ["r1"]),
            ]
        ]

    def extract_steps(self, image, system_prompt, instruction):
        del image, system_prompt, instruction
        self.calls += 1
        return ProviderResult(
            steps=[
                mkstep("s1", "Eq(2*x + 4, 10)", K.EQUATION, R.GIVEN),
                mkstep("s2", "Eq(2*x, 6)", K.EQUATION, R.EQUIVALENT, ("s1",)),
                mkstep("s3", "Eq(x, 4)", K.EQUATION, R.EQUIVALENT, ("s2",)),  # wrong: x = 3
            ],
            usage=Usage(endpoint="recognize", model=self.model, cost_usd=0.05, input_tokens=900),
        )

    def restructure_step(self, system_prompt, instruction):
        del system_prompt
        self.calls += 1
        self.instructions.append(instruction)
        if self.fail:
            raise ProviderError("El API respondió 529: saturado")
        sympy_text, parents = self.rebuilt
        step = mkstep("made-up-id", sympy_text, K.EQUATION, R.EQUIVALENT, tuple(parents))
        return ProviderResult(
            steps=[
                step.model_copy(update={"latex": "what the model felt like", "confidence": 0.2})
            ],
            usage=Usage(endpoint="correct", model=self.model, cost_usd=0.01),
        )

    def write_hint(self, system_prompt, instruction, image):
        self.calls += 1
        self.instructions.append(system_prompt.text + instruction)
        self.hint_images.append(image)
        step_id, error_type, text = self.hint
        return HintDraft(
            step_id=step_id,
            error_type=error_type,
            hint=text,
            usage=Usage(endpoint="hint", model=self.model, cost_usd=0.02),
        )

    def explain(self, system_prompt, instruction, image):
        del image
        self.calls += 1
        self.instructions.append(system_prompt.text + instruction)
        latex, sympy_text = self.explanation["corrected"] or (None, None)
        return ExplanationDraft(
            overview="Es una ecuación lineal: se despeja la incógnita.",
            notes=list(self.explanation["notes"]),
            suspect_step_id=self.explanation["suspect"],
            corrected_latex=latex,
            corrected_sympy=sympy_text,
            next_step="",
            takeaway="Lo que haces de un lado, hazlo del otro.",
            usage=Usage(endpoint="explain", model=self.model, cost_usd=0.03),
        )

    def solve(self, system_prompt, instruction, image):
        del system_prompt, image
        self.calls += 1
        self.instructions.append(instruction)
        answer = self.solutions.pop(0) if len(self.solutions) > 1 else self.solutions[0]
        steps = [
            mkstep(i, text, K.EQUATION, rel, tuple(parents)) for i, text, rel, parents in answer
        ]
        return SolutionDraft(
            goal="Despejar x.",
            method="Operaciones inversas en ambos lados.",
            steps=steps,
            whys={step.id: f"porque {step.id}" for step in steps},
            answer="$x = 3$",
            check="Sustituyendo: $2(3) + 4 = 10$.",
            usage=Usage(endpoint="solve", model=self.model, cost_usd=0.04),
        )


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 200), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def settings(tmp_path):
    return Settings(
        anthropic_api_key="test",
        app_token=TOKEN,
        data_dir=tmp_path / "data",
        monthly_budget_usd=1.0,
        recognition_cache_enabled=False,
    )


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def client(settings, provider):
    return TestClient(create_app(settings, provider))


def post_check(client, **overrides):
    request = {
        "headers": AUTH,
        "data": {"subject": "general"},
        "files": {"image": ("selection.png", png(), "image/png")},
    }
    request.update(overrides)
    return client.post("/api/check", **request)


def test_every_endpoint_requires_the_token(client, provider):
    assert client.get("/api/health").status_code == 401
    assert client.get("/api/usage", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert post_check(client, headers={}).status_code == 401
    assert provider.calls == 0
    assert client.get("/api/health", headers=AUTH).json() == {"ok": True}


def test_an_unconfigured_token_refuses_everything(settings, provider):
    settings.app_token = ""
    client = TestClient(create_app(settings, provider))
    assert client.get("/api/health", headers={"Authorization": "Bearer "}).status_code == 503


def test_check_reads_verifies_and_stores_the_review(client, settings, provider):
    response = post_check(client)
    assert response.status_code == 200, response.text
    body = response.json()

    statuses = {s["step_id"]: s["status"] for s in body["verification"]["steps"]}
    assert statuses["s2"] == "correct"
    assert statuses["s3"] == "error"
    assert [s["id"] for s in body["recognition"]["steps"]] == ["s1", "s2", "s3"]
    assert body["cost_usd"] == 0.05
    assert body["usage"] == {"month_spend_usd": 0.05, "budget_usd": 1.0, "checks_this_month": 1}

    with Session(make_engine(settings.resolved_database_url)) as db:
        stored = db.exec(select(Check)).one()
        assert stored.id == body["id"] and stored.subject == "general"
        assert db.exec(select(UsageLog)).one().cost_usd == 0.05
    assert (settings.data_dir / "images" / f"{body['id']}.png").is_file()


def test_the_monthly_budget_stops_calls_before_they_are_made(client, settings, provider):
    with Session(make_engine(settings.resolved_database_url)) as db:
        db.add(UsageLog(endpoint="check", model="fake-model", cost_usd=1.0))
        db.commit()

    response = post_check(client)

    assert response.status_code == 402
    assert "límite mensual" in response.json()["detail"]
    assert provider.calls == 0


def test_bad_requests_are_refused_without_calling_the_model(client, settings, provider):
    assert post_check(client, data={"subject": "no-existe"}).status_code == 404
    not_an_image = {"image": ("x.png", b"definitely not a png", "image/png")}
    assert post_check(client, files=not_an_image).status_code == 400
    assert provider.calls == 0
    # A rejected upload leaves nothing behind.
    assert list((settings.data_dir / "images").iterdir()) == []


def test_cors_only_admits_the_notebook(client):
    allowed = client.options(
        "/api/check",
        headers={
            "Origin": "https://paso-libreta.paso-frontend.workers.dev",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert allowed.headers["access-control-allow-origin"].startswith("https://paso-libreta")
    stranger = client.options(
        "/api/check",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in stranger.headers


# --- correcting a misread step (2b) ------------------------------------------


def statuses(body) -> dict[str, str]:
    return {s["step_id"]: s["status"] for s in body["verification"]["steps"]}


def correct(client, check_id, step_id, latex, **overrides):
    request = {"headers": AUTH, "data": {"latex": latex}}
    request.update(overrides)
    return client.post(f"/api/checks/{check_id}/steps/{step_id}", **request)


def test_correcting_a_step_restructures_it_and_verifies_again(client, settings, provider):
    first = post_check(client).json()
    assert statuses(first)["s3"] == "error"

    response = correct(client, first["id"], "s3", "  x = 3 ")
    assert response.status_code == 200, response.text
    body = response.json()

    assert statuses(body) == {"s1": "correct", "s2": "correct", "s3": "correct"}
    fixed = body["recognition"]["steps"][2]
    # The text is the student's and the id is ours, whatever the model answered.
    assert (fixed["id"], fixed["latex"], fixed["sympy"]) == ("s3", "x = 3", "Eq(x, 3)")
    assert fixed["confidence"] == 1.0
    assert body["corrected"] == ["s3"]
    assert body["cost_usd"] == 0.01
    assert body["usage"]["month_spend_usd"] == 0.06
    assert "x = 3" in provider.instructions[-1] and "Eq(2*x, 6)" in provider.instructions[-1]

    with Session(make_engine(settings.resolved_database_url)) as db:
        stored = db.exec(select(Check)).one()
        # What the model first read is kept: it is what the test bank measures.
        assert '"Eq(x, 4)"' in stored.steps_json
        assert '"Eq(x, 3)"' in stored.corrected_steps_json
        assert sorted(u.endpoint for u in db.exec(select(UsageLog)).all()) == ["check", "correct"]


def test_a_correction_the_model_cannot_structure_is_never_an_error(client, provider):
    first = post_check(client).json()
    provider.rebuilt = (None, ["s2"])
    assert statuses(correct(client, first["id"], "s3", "x \\approx 3").json())["s3"] == (
        "unverifiable"
    )
    # Nor does nonsense from the model: unparseable SymPy and a link to a later step.
    provider.rebuilt = ("Eq(x, ", ["s3", "s9"])
    body = correct(client, first["id"], "s2", "2x = 6 \\,").json()
    assert statuses(body)["s2"] == "unverifiable"
    assert body["recognition"]["steps"][1]["derives_from"] == ["s1"]


def test_corrections_are_refused_before_spending(client, settings, provider):
    first = post_check(client).json()
    calls = provider.calls

    assert correct(client, "nope", "s3", "x = 3").status_code == 404
    assert correct(client, first["id"], "s9", "x = 3").status_code == 404
    assert correct(client, first["id"], "s3", "   ").status_code == 422
    assert correct(client, first["id"], "s3", "x" * 5000).status_code == 422
    assert correct(client, first["id"], "s3", "x = 3", headers={}).status_code == 401
    # Saving the same text changes nothing and costs nothing.
    same = correct(client, first["id"], "s3", " Eq(x, 4) ")
    assert (
        same.status_code == 200 and same.json()["cost_usd"] == 0 and same.json()["corrected"] == []
    )

    with Session(make_engine(settings.resolved_database_url)) as db:
        db.add(UsageLog(endpoint="check", model="fake-model", cost_usd=1.0))
        db.commit()
    assert correct(client, first["id"], "s3", "x = 3").status_code == 402
    assert provider.calls == calls


def test_a_failed_correction_leaves_the_review_untouched(client, settings, provider):
    first = post_check(client).json()
    provider.fail = True

    response = correct(client, first["id"], "s3", "x = 3")

    assert response.status_code == 502 and "529" in response.json()["detail"]
    with Session(make_engine(settings.resolved_database_url)) as db:
        assert db.exec(select(Check)).one().corrected_steps_json is None


# --- level-1 hint (2b) --------------------------------------------------------


def ask_hint(client, check_id, **overrides):
    request = {"headers": AUTH}
    request.update(overrides)
    return client.post(f"/api/checks/{check_id}/hint", **request)


def test_the_hint_points_where_the_verifier_found_the_error(client, settings, provider):
    first = post_check(client).json()
    # The model names a step the verifier proved correct. It does not get a say.
    provider.hint = ("s1", "arithmetic", "Revisa la división del paso 3.")

    response = ask_hint(client, first["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    hint = body["hint"]

    assert (hint["step_id"], hint["basis"]) == ("s3", "verified")
    assert "paso 3" in hint["verified"] and "verificador simbólico" in hint["verified"]
    assert hint["hint"] == "Revisa la división del paso 3."
    assert (hint["error_type"], hint["error_label"]) == ("arithmetic", "Error aritmético")
    assert body["cost_usd"] == 0.02
    # The model was told which step fails, given the subject's taxonomy and shown the ink.
    sent = provider.instructions[-1]
    assert "id s3" in sent and "`arithmetic`" in sent and "No des la respuesta" in sent
    assert provider.hint_images[-1] is not None

    # Asking again returns the stored hint without paying twice.
    calls = provider.calls
    again = ask_hint(client, first["id"]).json()
    assert again["hint"] == hint and again["cost_usd"] == 0 and provider.calls == calls
    with Session(make_engine(settings.resolved_database_url)) as db:
        assert [u.cost_usd for u in db.exec(select(UsageLog)).all()] == [0.05, 0.02]


def test_an_error_type_outside_the_subject_taxonomy_is_dropped(client, provider):
    first = post_check(client).json()
    provider.hint = ("s3", "made_up_type", "Mira el último despeje.")

    hint = ask_hint(client, first["id"]).json()["hint"]

    assert hint["error_type"] is None and hint["error_label"] is None
    assert hint["hint"] == "Mira el último despeje."


def test_the_model_cannot_flag_a_step_the_verifier_proved_correct(client, provider):
    first = post_check(client).json()
    fixed = correct(client, first["id"], "s3", "x = 3").json()
    assert "error" not in statuses(fixed).values()
    # One step the verifier cannot check, so the model is consulted.
    provider.rebuilt = (None, ["s2"])
    correct(client, first["id"], "s3", "\\text{entonces } x = 3")
    provider.hint = ("s2", "algebra", "El paso 2 está mal despejado.")

    hint = ask_hint(client, first["id"]).json()["hint"]

    assert (hint["step_id"], hint["basis"], hint["hint"]) == (None, "none", "")
    assert hint["error_type"] is None
    assert "no encontró errores" in hint["verified"]


def test_a_doubt_about_an_unverifiable_step_is_labelled_as_opinion(client, provider):
    first = post_check(client).json()
    provider.rebuilt = (None, ["s2"])
    correct(client, first["id"], "s3", "\\text{por lo tanto } x = 4")
    provider.hint = ("s3", "arithmetic", "Vuelve a hacer la división del paso 3.")

    hint = ask_hint(client, first["id"]).json()["hint"]

    assert (hint["step_id"], hint["basis"]) == ("s3", "model_opinion")
    assert "Un paso no se pudo comprobar" in hint["verified"]
    # And when the model sees nothing wrong, nothing is invented.
    correct(client, first["id"], "s3", "\\text{por lo tanto } x = 3")
    provider.hint = (None, None, "")
    assert ask_hint(client, first["id"]).json()["hint"]["basis"] == "none"


def test_a_fully_verified_review_gets_no_paid_hint(client, provider):
    first = post_check(client).json()
    correct(client, first["id"], "s3", "x = 3")
    calls = provider.calls

    body = ask_hint(client, first["id"]).json()

    assert body["hint"]["basis"] == "none" and body["hint"]["hint"] == ""
    assert "todos los pasos" in body["hint"]["verified"]
    assert body["cost_usd"] == 0 and provider.calls == calls


def test_correcting_a_step_discards_the_stale_hint(client, provider):
    first = post_check(client).json()
    assert ask_hint(client, first["id"]).json()["hint"]["step_id"] == "s3"

    assert correct(client, first["id"], "s3", "x = 3").json()["hint"] is None


def test_hints_respect_token_budget_and_unknown_reviews(client, settings, provider):
    first = post_check(client).json()
    calls = provider.calls
    assert ask_hint(client, first["id"], headers={}).status_code == 401
    assert ask_hint(client, "nope").status_code == 404
    with Session(make_engine(settings.resolved_database_url)) as db:
        db.add(UsageLog(endpoint="check", model="fake-model", cost_usd=1.0))
        db.commit()
    assert ask_hint(client, first["id"]).status_code == 402
    assert provider.calls == calls


# --- level 2: the explanation -------------------------------------------------


def ask(client, check_id, what, **overrides):
    request = {"headers": AUTH}
    request.update(overrides)
    return client.post(f"/api/checks/{check_id}/{what}", **request)


def test_the_explanation_comments_the_steps_and_checks_its_own_correction(client, provider):
    first = post_check(client).json()

    response = ask(client, first["id"], "level/2")
    assert response.status_code == 200, response.text
    body = response.json()
    told = body["explanation"]

    assert (told["failing_step_id"], told["basis"]) == ("s3", "verified")
    # Comments on steps that do not exist are dropped.
    assert [n["step_id"] for n in told["notes"]] == ["s2", "s3"]
    # The corrected step went through the verifier before being shown.
    assert told["corrected"] == {
        "step_id": "s3",
        "latex": "x = 3",
        "sympy": "Eq(x, 3)",
        "verified": True,
        "detail": told["corrected"]["detail"],
    }
    assert told["correction_rejected"] is False
    assert body["cost_usd"] == 0.03
    sent = provider.instructions[-1]
    assert "id s3" in sent and "nunca digas que está mal" in sent and "Derivative" in sent

    # Asking again is free.
    calls = provider.calls
    assert ask(client, first["id"], "level/2").json()["cost_usd"] == 0
    assert provider.calls == calls


def test_a_wrong_correction_from_the_model_is_never_shown(client, provider):
    first = post_check(client).json()
    provider.explanation["corrected"] = ("x = 5", "Eq(x, 5)")  # still wrong

    told = ask(client, first["id"], "level/2").json()["explanation"]

    assert told["corrected"] is None and told["correction_rejected"] is True
    assert told["failing_step_id"] == "s3"


def test_a_correction_that_cannot_be_checked_is_labelled_unverified(client, provider):
    first = post_check(client).json()
    provider.explanation["corrected"] = ("x = 3", None)

    told = ask(client, first["id"], "level/2").json()["explanation"]

    assert told["corrected"]["verified"] is False


def test_the_explanation_cannot_doubt_a_step_that_was_proved(client, provider):
    first = post_check(client).json()
    correct(client, first["id"], "s3", "x = 3")  # now everything checks out
    provider.explanation.update(suspect="s2", corrected=("2x = 5", "Eq(2*x, 5)"))

    told = ask(client, first["id"], "level/2").json()["explanation"]

    assert (told["failing_step_id"], told["basis"]) == (None, "none")
    assert told["corrected"] is None and told["correction_rejected"] is False
    assert told["overview"]  # it still explains why the development is right


def test_a_doubt_about_an_unchecked_step_is_an_opinion_in_the_explanation(client, provider):
    first = post_check(client).json()
    provider.rebuilt = (None, ["s2"])
    correct(client, first["id"], "s3", "\\text{entonces } x = 4")
    provider.explanation.update(suspect="s3", corrected=("x = 3", "Eq(x, 3)"))

    told = ask(client, first["id"], "level/2").json()["explanation"]

    assert (told["failing_step_id"], told["basis"]) == ("s3", "model_opinion")
    assert told["corrected"]["verified"] is True  # x = 3 does follow from 2x = 6


# --- level 3: the solution ----------------------------------------------------


def test_the_solution_starts_from_the_students_data_and_is_verified(client, settings, provider):
    first = post_check(client).json()

    response = ask(client, first["id"], "solve")
    assert response.status_code == 200, response.text
    body = response.json()
    solution = body["solution"]

    assert solution["verified"] is True and solution["attempts"] == 1
    assert (solution["checked_steps"], solution["wrong_steps"]) == (2, 0)
    steps = solution["steps"]
    # The problem data is the student's own first line, not something the model chose.
    assert steps[0]["given"] is True and steps[0]["step"]["sympy"] == "Eq(2*x + 4, 10)"
    assert [s["step"]["id"] for s in steps] == ["g1", "r1", "r2"]
    assert [s["status"] for s in steps] == ["correct", "correct", "correct"]
    assert steps[2]["why"] == "porque r2"
    assert body["cost_usd"] == 0.04
    assert "g1 | latex" in provider.instructions[-1]

    with Session(make_engine(settings.resolved_database_url)) as db:
        assert db.exec(select(Check)).one().max_level_shown == 3
    calls = provider.calls
    assert ask(client, first["id"], "solve").json()["cost_usd"] == 0 and provider.calls == calls


def test_a_wrong_solution_gets_one_chance_to_be_fixed(client, provider):
    first = post_check(client).json()
    provider.solutions = [
        [("r1", "Eq(2*x, 6)", R.EQUIVALENT, ["g1"]), ("r2", "Eq(x, 4)", R.RESULT, ["r1"])],
        [("r1", "Eq(2*x, 6)", R.EQUIVALENT, ["g1"]), ("r2", "Eq(x, 3)", R.RESULT, ["r1"])],
    ]

    body = ask(client, first["id"], "solve").json()

    assert body["solution"]["verified"] is True and body["solution"]["attempts"] == 2
    assert body["cost_usd"] == 0.08  # both calls are paid for and counted
    assert "no pasó la comprobación" in provider.instructions[-1]
    assert "r2" in provider.instructions[-1]


def test_a_solution_that_stays_wrong_is_shown_with_a_warning_not_a_badge(client, provider):
    first = post_check(client).json()
    provider.solutions = [
        [("r1", "Eq(2*x, 6)", R.EQUIVALENT, ["g1"]), ("r2", "Eq(x, 4)", R.RESULT, ["r1"])]
    ]

    solution = ask(client, first["id"], "solve").json()["solution"]

    assert solution["verified"] is False and solution["attempts"] == 2
    assert solution["wrong_steps"] == 1
    assert solution["steps"][-1]["status"] == "error"


def test_the_model_cannot_pass_its_answer_off_as_problem_data(client, provider):
    first = post_check(client).json()
    # Declared "given", the verifier would accept x = 4 without looking at it.
    provider.solutions = [[("r1", "Eq(x, 4)", R.GIVEN, [])]]

    solution = ask(client, first["id"], "solve").json()["solution"]

    assert solution["verified"] is False
    assert solution["steps"][-1]["step"]["relation"] != "given"
    assert solution["steps"][-1]["status"] != "correct"


def test_explanations_and_solutions_follow_corrections_budget_and_token(client, settings, provider):
    first = post_check(client).json()
    ask(client, first["id"], "level/2")
    ask(client, first["id"], "solve")

    fixed = correct(client, first["id"], "s3", "x = 3").json()
    assert fixed["explanation"] is None and fixed["solution"] is None

    calls = provider.calls
    for what in ("level/2", "solve"):
        assert ask(client, first["id"], what, headers={}).status_code == 401
        assert ask(client, "nope", what).status_code == 404
    with Session(make_engine(settings.resolved_database_url)) as db:
        db.add(UsageLog(endpoint="check", model="fake-model", cost_usd=1.0))
        db.commit()
    for what in ("level/2", "solve"):
        assert ask(client, first["id"], what).status_code == 402
    assert provider.calls == calls
