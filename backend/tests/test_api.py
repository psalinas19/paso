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
from app.llm.base import (
    ExerciseDraft,
    ExplanationDraft,
    HintDraft,
    PracticeDraft,
    ProviderError,
    ProviderResult,
    SolutionDraft,
)
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
        #: The topic the model files the mistake under.
        self.hint_topic = None
        self.instructions: list[str] = []
        self.hint_images: list[object] = []
        self.fail = False
        self.chats: list[tuple] = []
        #: What the next page reads as; None for the default development with a mistake.
        self.page = None
        #: Practice exercises the model writes: (slot, statement, data, answer).
        #: The last one is broken: its answer does not solve its own equation.
        self.exercises = [
            (1, "Resuelve $2x + 4 = 10$.", ["Eq(2*x + 4, 10)"], "Eq(x, 3)"),
            (2, "Resuelve $3x - 6 = 0$.", ["Eq(3*x - 6, 0)"], "Eq(x, 2)"),
            (3, "Resuelve $x + 1 = 5$.", ["Eq(x + 1, 5)"], "Eq(x, 4)"),
            (4, "Resuelve $x - 1 = 5$.", ["Eq(x - 1, 5)"], "Eq(x, 7)"),
        ]
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
            steps=self.page
            or [
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
            topic=self.hint_topic,
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

    def write_exercises(self, system_prompt, instruction):
        self.calls += 1
        self.instructions.append(system_prompt.text + instruction)
        if self.fail:
            raise ProviderError("El API respondió 529: saturado")
        drafts = [
            ExerciseDraft(
                slot=slot,
                statement=statement,
                data=[mkstep(f"g{i}", d, K.EQUATION, R.GIVEN) for i, d in enumerate(data, 1)],
                answer=mkstep("r1", answer, K.EQUATION, R.RESULT, ("g1",)),
            )
            for slot, statement, data, answer in self.exercises
        ]
        return PracticeDraft(
            exercises=drafts,
            usage=Usage(endpoint="practice", model=self.model, cost_usd=0.03),
        )

    def chat(self, system_prompt, context, turns, image):
        self.calls += 1
        self.chats.append((system_prompt.text, context, list(turns), image))
        if self.fail:
            raise ProviderError("El API respondió 529: saturado")
        yield "Porque al dividir "
        yield "entre 2 da $x = 3$."
        yield Usage(endpoint="chat", model=self.model, cost_usd=0.006)

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


# --- confirming a reading, timings, the effort knob ---------------------------


def test_saving_a_doubtful_reading_unchanged_confirms_it_for_free(client, settings, provider):
    low = mkstep("s2", "Eq(2*x, 6)", K.EQUATION, R.EQUIVALENT, ("s1",), confidence=0.4)
    original = provider.extract_steps

    def doubtful(image, system_prompt, instruction):
        result = original(image, system_prompt, instruction)
        result.steps[1] = low
        return result

    provider.extract_steps = doubtful
    first = post_check(client).json()
    assert first["recognition"]["steps"][1]["confidence"] == 0.4
    calls = provider.calls

    body = correct(client, first["id"], "s2", "Eq(2*x, 6)").json()

    assert body["recognition"]["steps"][1]["confidence"] == 1.0
    assert body["cost_usd"] == 0 and provider.calls == calls
    assert body["corrected"] == []  # confirmed, not rewritten
    assert statuses(body) == statuses(first)


def test_every_answer_says_where_the_time_went(client, provider):
    original = provider.extract_steps

    def slow(image, system_prompt, instruction):
        result = original(image, system_prompt, instruction)
        result.usage.latency_ms = 4200
        return result

    provider.extract_steps = slow
    body = post_check(client).json()

    assert body["model_seconds"] == 4.2
    assert body["verify_seconds"] >= 0
    # A stored answer cost no time at the model.
    ask(client, body["id"], "solve")
    assert ask(client, body["id"], "solve").json()["model_seconds"] == 0


def test_the_effort_setting_reaches_the_provider(monkeypatch):
    from app.cli_common import build_provider

    built = {}
    monkeypatch.setattr(
        "app.cli_common.AnthropicProvider", lambda **kwargs: built.update(kwargs) or "provider"
    )
    build_provider(Settings(anthropic_api_key="k", anthropic_effort=" Medium "))
    assert built["effort"] == "medium"
    build_provider(Settings(anthropic_api_key="k", anthropic_effort=""))
    assert built["effort"] is None  # untouched: the API default applies


def test_the_notebook_can_ask_for_speed_and_the_client_is_reused(settings, monkeypatch):
    built = []
    inner = FakeProvider()

    def fake_build(_settings, effort=None):
        built.append(effort)
        return inner

    monkeypatch.setattr("app.api.main.build_provider", fake_build)
    client = TestClient(create_app(settings))  # no provider injected: the real path

    first = post_check(client, data={"subject": "general", "effort": "low"})
    assert first.status_code == 200, first.text
    post_check(client, data={"subject": "general", "effort": "low"})
    ask(client, first.json()["id"], "solve", data={"effort": "medium"})
    post_check(client)  # no preference: whatever .env says

    # One client per level, built once, not one per request.
    assert built == ["low", "medium", None]
    assert post_check(client, data={"subject": "general", "effort": "max"}).status_code == 422
    assert built == ["low", "medium", None]


# --- chat about a review (phase 3) --------------------------------------------


def events_of(response) -> list[tuple[str, dict]]:
    """The server-sent events of a response, as (event, data) pairs."""
    import json

    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def say(client, check_id, message, **overrides):
    request = {"headers": AUTH, "data": {"message": message}}
    request.update(overrides)
    return client.post(f"/api/checks/{check_id}/chat", **request)


def test_the_tutor_answers_in_pieces_and_the_conversation_is_kept(client, settings, provider):
    first = post_check(client).json()
    ask(client, first["id"], "level/2")

    response = say(client, first["id"], "  ¿Por qué está mal el paso 3?  ")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = events_of(response)

    assert [name for name, _ in events] == ["delta", "delta", "done"]
    assert "".join(data["text"] for name, data in events if name == "delta") == (
        "Porque al dividir entre 2 da $x = 3$."
    )
    assert events[-1][1]["cost_usd"] == 0.006
    assert events[-1][1]["usage"]["month_spend_usd"] == 0.086

    # The tutor was told the state of the exercise, apart from its rules.
    prompt, context, turns, image = provider.chats[-1]
    assert "El verificador manda" in prompt and "Eq(x, 4)" not in prompt
    assert "Eq(x, 4)" in context and "id s3" in context and "Explicación que ya recibió" in context
    assert [(t.role, t.content) for t in turns] == [("user", "¿Por qué está mal el paso 3?")]
    assert image is not None

    # A second question carries the first exchange with it.
    say(client, first["id"], "¿Y cómo lo evito?")
    assert [t.role for t in provider.chats[-1][2]] == ["user", "assistant", "user"]

    history = client.get(f"/api/checks/{first['id']}/chat", headers=AUTH).json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    assert history[1]["content"] == "Porque al dividir entre 2 da $x = 3$."
    with Session(make_engine(settings.resolved_database_url)) as db:
        assert [u.endpoint for u in db.exec(select(UsageLog)).all()].count("chat") == 2


def test_a_failed_answer_is_reported_and_leaves_nothing_behind(client, provider):
    first = post_check(client).json()
    provider.fail = True

    events = events_of(say(client, first["id"], "¿Hola?"))

    assert [name for name, _ in events] == ["error"]
    assert "529" in events[0][1]["detail"]
    # The question was not stored, so asking again does not double it.
    assert client.get(f"/api/checks/{first['id']}/chat", headers=AUTH).json()["messages"] == []


def test_chat_respects_token_budget_and_limits(client, settings, provider):
    first = post_check(client).json()
    calls = provider.calls
    assert say(client, first["id"], "hola", headers={}).status_code == 401
    assert say(client, "nope", "hola").status_code == 404
    assert say(client, first["id"], "   ").status_code == 422
    assert say(client, first["id"], "x" * 5000).status_code == 422
    assert client.get("/api/checks/nope/chat", headers=AUTH).status_code == 404
    with Session(make_engine(settings.resolved_database_url)) as db:
        db.add(UsageLog(endpoint="check", model="fake-model", cost_usd=1.0))
        db.commit()
    assert say(client, first["id"], "hola").status_code == 402
    assert provider.calls == calls


# --- the error bank (4a) ------------------------------------------------------


def save_error(client, check_id, step_id, **fields):
    body = {"check_id": check_id, "step_id": step_id, **fields}
    return client.post("/api/errors", headers=AUTH, json=body)


def bank(client) -> list[dict]:
    return client.get("/api/errors", headers=AUTH).json()["errors"]


def test_a_proved_mistake_is_saved_with_what_the_verifier_said(client, provider):
    first = post_check(client).json()

    response = save_error(client, first["id"], "s3", subject_name="Álgebra 2026-2")
    assert response.status_code == 200, response.text
    entry = response.json()

    assert (entry["check_id"], entry["step_id"]) == (first["id"], "s3")
    assert (entry["subject"], entry["subject_name"]) == ("general", "Álgebra 2026-2")
    assert entry["proved"] is True and entry["resolved"] is False
    assert entry["latex"] and entry["detail"]
    # No hint was asked for, so nothing proposed a classification, and nothing was paid.
    assert entry["error_type"] is None and entry["topic"] is None
    assert provider.calls == 1
    assert entry["created_at"].endswith(("Z", "+00:00"))
    assert bank(client) == [entry]

    # Saving the same step again changes the entry; it does not add another.
    again = save_error(client, first["id"], "s3", error_type="arithmetic").json()
    assert again["id"] == entry["id"] and again["error_label"] == "Error aritmético"
    assert again["subject_name"] == "Álgebra 2026-2"
    assert len(bank(client)) == 1
    # Every answer about the review now says which of its steps are in the bank.
    assert [e["id"] for e in ask_hint(client, first["id"]).json()["errors"]] == [entry["id"]]


def test_a_step_that_was_proved_correct_cannot_enter_the_bank(client):
    first = post_check(client).json()
    assert statuses(first)["s2"] == "correct"

    response = save_error(client, first["id"], "s2")

    assert response.status_code == 422 and "correcto" in response.json()["detail"]
    assert bank(client) == []


def test_the_bank_takes_the_classification_the_hint_proposed(client, provider):
    first = post_check(client, data={"subject": "ed"}).json()
    provider.hint = ("s3", "algebra", "Revisa el despeje.")
    provider.hint_topic = "edo-lineal"
    hint = ask_hint(client, first["id"]).json()["hint"]
    assert hint["topic"] == "edo-lineal"

    entry = save_error(client, first["id"], "s3").json()

    assert (entry["error_type"], entry["error_label"]) == ("algebra", "Álgebra")
    assert entry["topic"] == "edo-lineal"
    # With no name sent, the bank files it under the subject's own name.
    assert entry["subject_name"] == "Ecuaciones Diferenciales"


def test_a_topic_outside_the_subject_list_is_dropped_from_the_hint(client, provider):
    first = post_check(client, data={"subject": "ed"}).json()
    provider.hint = ("s3", "algebra", "Revisa el despeje.")
    provider.hint_topic = "made-up-topic"

    assert ask_hint(client, first["id"]).json()["hint"]["topic"] is None


def test_an_entry_can_be_reclassified_marked_overcome_and_removed(client):
    first = post_check(client).json()
    entry = save_error(client, first["id"], "s3", error_type="sign", topic="despejes").json()
    url = f"/api/errors/{entry['id']}"

    changed = client.patch(url, headers=AUTH, json={"error_type": "arithmetic", "resolved": True})
    assert changed.status_code == 200, changed.text
    assert (changed.json()["error_type"], changed.json()["resolved"]) == ("arithmetic", True)
    assert changed.json()["topic"] == "despejes"  # not sent: left alone

    cleared = client.patch(url, headers=AUTH, json={"error_type": None, "topic": ""}).json()
    assert cleared["error_type"] is None and cleared["topic"] is None
    assert cleared["resolved"] is True

    assert client.patch(url, headers=AUTH, json={"error_type": "nope"}).status_code == 422
    assert client.patch(url, headers=AUTH, json={"topic": "x" * 61}).status_code == 422
    assert client.patch(url, headers=AUTH, json={"latex": "x"}).status_code == 422

    assert client.delete(url, headers=AUTH).json() == {"ok": True}
    assert bank(client) == []
    assert client.delete(url, headers=AUTH).status_code == 404
    assert client.patch(url, headers=AUTH, json={"resolved": False}).status_code == 404


def test_fixing_a_misread_step_takes_its_false_mistake_out_of_the_bank(client, provider):
    first = post_check(client).json()
    save_error(client, first["id"], "s3")
    assert len(bank(client)) == 1

    # The line really said x = 3: the "mistake" was the reading, not the student.
    provider.rebuilt = ("Eq(x, 3)", ["s2"])
    body = correct(client, first["id"], "s3", "x = 3").json()

    assert statuses(body)["s3"] == "correct"
    assert body["errors"] == [] and bank(client) == []


def test_a_correction_that_is_still_wrong_keeps_the_entry_up_to_date(client, provider):
    first = post_check(client).json()
    save_error(client, first["id"], "s3")

    provider.rebuilt = ("Eq(x, 5)", ["s2"])
    body = correct(client, first["id"], "s3", "x = 5").json()

    assert statuses(body)["s3"] == "error"
    assert [e["latex"] for e in body["errors"]] == ["x = 5"]
    assert bank(client)[0]["proved"] is True


def test_the_bank_refuses_unknown_reviews_steps_types_and_callers(client):
    first = post_check(client).json()

    assert save_error(client, "nope", "s3").status_code == 404
    assert save_error(client, first["id"], "s9").status_code == 404
    assert save_error(client, first["id"], "s3", error_type="made_up").status_code == 422
    assert save_error(client, first["id"], "s3", subject_name="x" * 81).status_code == 422
    assert bank(client) == []
    for call in (
        lambda: client.get("/api/errors"),
        lambda: client.get("/api/taxonomy"),
        lambda: client.post("/api/errors", json={"check_id": first["id"], "step_id": "s3"}),
        lambda: client.patch("/api/errors/1", json={"resolved": True}),
        lambda: client.delete("/api/errors/1"),
    ):
        assert call().status_code == 401


def test_the_taxonomy_lists_every_subject_for_the_pickers(client):
    subjects = {s["slug"]: s for s in client.get("/api/taxonomy", headers=AUTH).json()["subjects"]}

    assert {"general", "ed", "circuitos1"} <= set(subjects)
    assert "edo-lineal" in subjects["ed"]["topics"]
    assert {"id": "sign", "label": "Error de signo"}.items() <= subjects["ed"]["error_types"][
        0
    ].items()


def test_the_browser_may_send_json_and_use_patch_and_delete(client):
    for method in ("PATCH", "DELETE", "POST"):
        allowed = client.options(
            "/api/errors/1",
            headers={
                "Origin": "https://paso-libreta.paso-frontend.workers.dev",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert allowed.status_code == 200, method
        assert method in allowed.headers["access-control-allow-methods"]


# --- practice mode (4b) -------------------------------------------------------

CLEAN = [
    ("s1", "Eq(2*x + 4, 10)", R.GIVEN, ()),
    ("s2", "Eq(2*x, 6)", R.EQUIVALENT, ("s1",)),
    ("s3", "Eq(x, 3)", R.EQUIVALENT, ("s2",)),
]


def page(lines):
    return [mkstep(i, text, K.EQUATION, rel, parents) for i, text, rel, parents in lines]


def practice(client, provider, **body):
    """A round of practice built on one saved arithmetic mistake in «Álgebra»."""
    first = post_check(client).json()
    save_error(client, first["id"], "s3", subject_name="Álgebra", error_type="arithmetic")
    request = {"subject_name": "Álgebra", **body}
    response = client.post("/api/review/generate", headers=AUTH, json=request)
    assert response.status_code == 200, response.text
    return response.json()


def attempt(client, exercise_id):
    return post_check(client, data={"subject": "general", "exercise_id": exercise_id}).json()


def test_practice_is_built_from_the_bank_and_drops_a_broken_exercise(client, provider):
    made = practice(client, provider, count=4)

    sent = provider.instructions[-1]
    # Our code, not the model, decides what each exercise goes after.
    assert "Escribe 4 ejercicios" in sent and sent.count("Error aritmético (`arithmetic`)") == 4
    assert "Pasos suyos con ese error" in sent and "No copies su ejercicio" in sent
    # The fourth exercise's answer does not solve its own equation: it never reaches the student.
    assert [e["statement"] for e in made["exercises"]] == [
        "Resuelve $2x + 4 = 10$.",
        "Resuelve $3x - 6 = 0$.",
        "Resuelve $x + 1 = 5$.",
    ]
    assert {e["status"] for e in made["exercises"]} == {"pending"}
    assert {e["error_label"] for e in made["exercises"]} == {"Error aritmético"}
    # The expected result stays hidden until an attempt is handed in.
    assert all(e["answer_latex"] is None for e in made["exercises"])
    assert (made["subject"], made["subject_name"], made["exam"]) == ("general", "Álgebra", False)
    assert made["cost_usd"] == 0.03


def test_practice_needs_pending_mistakes_and_spends_nothing_without_them(client, provider):
    def generate(**body):
        return client.post("/api/review/generate", headers=AUTH, json=body)

    empty = generate(subject_name="Álgebra")
    assert empty.status_code == 422 and "banco de errores" in empty.json()["detail"]
    assert provider.calls == 0

    made = practice(client, provider)
    calls = provider.calls
    # An overcome mistake is not practised again.
    entry = bank(client)[0]
    client.patch(f"/api/errors/{entry['id']}", headers=AUTH, json={"resolved": True})
    assert generate(subject_name="Álgebra").status_code == 422
    assert generate(subject_name="Álgebra", count=9).status_code == 422
    assert generate(subject_name="Otra materia").status_code == 422
    assert provider.calls == calls and made["exercises"]
    assert client.post("/api/review/generate", json={"subject_name": "x"}).status_code == 401


def test_a_failed_model_call_or_no_usable_exercise_is_reported(client, provider):
    first = post_check(client).json()
    save_error(client, first["id"], "s3", subject_name="Álgebra")
    provider.exercises = [(1, "Resuelve $x - 1 = 5$.", ["Eq(x - 1, 5)"], "Eq(x, 7)")]

    nothing = client.post("/api/review/generate", headers=AUTH, json={"subject_name": "Álgebra"})
    assert nothing.status_code == 502 and "comprobación" in nothing.json()["detail"]

    provider.fail = True
    failed = client.post("/api/review/generate", headers=AUTH, json={"subject_name": "Álgebra"})
    assert failed.status_code == 502 and "529" in failed.json()["detail"]


def test_the_first_reviewed_attempt_decides_an_exercise(client, provider):
    made = practice(client, provider)
    one = made["exercises"][0]["id"]

    # The default page ends in x = 4: a mistake.
    body = attempt(client, one)
    assert body["exercise"]["status"] == "failed" and body["exercise"]["check_id"] == body["id"]
    assert body["progress"] == {
        "error_type": "arithmetic",
        "error_label": "Error aritmético",
        "streak": 0,
        "needed": 3,
        "overcome": False,
    }
    # Now that it is decided, the proved result can be shown.
    assert body["exercise"]["answer_latex"]

    # Doing it again with the answer in sight changes nothing.
    provider.page = page(CLEAN)
    again = attempt(client, one)
    assert again["exercise"]["status"] == "failed" and again["progress"] is None
    assert again["exercise"]["check_id"] == body["id"]


def test_three_clean_attempts_in_a_row_overcome_the_mistake(client, provider):
    made = practice(client, provider)
    provider.page = page(CLEAN)

    streaks = [attempt(client, e["id"])["progress"] for e in made["exercises"]]

    assert [p["streak"] for p in streaks] == [1, 2, 3]
    assert [p["overcome"] for p in streaks] == [False, False, True]
    assert [e["resolved"] for e in bank(client)] == [True]


def test_a_mistake_in_between_resets_the_streak(client, provider):
    made = practice(client, provider)
    first, second, third = (e["id"] for e in made["exercises"])
    provider.page = page(CLEAN)
    assert attempt(client, first)["progress"]["streak"] == 1
    provider.page = None  # the development with the mistake
    assert attempt(client, second)["progress"]["streak"] == 0
    provider.page = page(CLEAN)

    assert attempt(client, third)["progress"]["streak"] == 1
    assert [e["resolved"] for e in bank(client)] == [False]


def test_a_page_with_only_the_statement_is_not_an_attempt(client, provider):
    made = practice(client, provider)
    provider.page = page(CLEAN[:1])

    body = attempt(client, made["exercises"][0]["id"])

    assert body["exercise"]["status"] == "pending" and body["progress"] is None
    assert body["exercise"]["answer_latex"] is None
    # Outside exam mode, help on the bare statement is allowed.
    assert ask_hint(client, body["id"]).status_code == 200


def test_fixing_a_misread_line_decides_the_exercise_again(client, provider):
    made = practice(client, provider)
    body = attempt(client, made["exercises"][0]["id"])
    assert body["exercise"]["status"] == "failed"

    provider.rebuilt = ("Eq(x, 3)", ["s2"])
    fixed = correct(client, body["id"], "s3", "x = 3").json()

    assert fixed["exercise"]["status"] == "passed"
    assert fixed["progress"]["streak"] == 1


def test_exam_mode_withholds_help_until_an_attempt_is_handed_in(client, provider):
    made = practice(client, provider, exam=True)
    exercise = made["exercises"][0]
    assert exercise["exam"] is True
    provider.page = page(CLEAN[:1])
    bare = attempt(client, exercise["id"])
    calls = provider.calls

    for path in ("hint", "level/2", "solve"):
        refused = client.post(f"/api/checks/{bare['id']}/{path}", headers=AUTH)
        assert refused.status_code == 409 and "Modo examen" in refused.json()["detail"], path
    asked = client.post(
        f"/api/checks/{bare['id']}/chat", headers=AUTH, data={"message": "¿Cómo empiezo?"}
    )
    assert asked.status_code == 409 and provider.calls == calls

    provider.page = page(CLEAN)
    done = attempt(client, exercise["id"])
    assert done["exercise"]["status"] == "passed"
    # Handed in: help is open again, on either review of the exercise.
    assert client.post(f"/api/checks/{bare['id']}/solve", headers=AUTH).status_code == 200
    assert client.post(f"/api/checks/{done['id']}/level/2", headers=AUTH).status_code == 200


def test_a_review_of_an_unknown_exercise_is_refused_before_spending(client, provider):
    response = post_check(client, data={"subject": "general", "exercise_id": "nope"})

    assert response.status_code == 404 and provider.calls == 0
    # A review that attempts no exercise says so by saying nothing.
    plain = post_check(client).json()
    assert plain["exercise"] is None and plain["progress"] is None


# --- search (4c) --------------------------------------------------------------


def find(client, q):
    response = client.get("/api/search", headers=AUTH, params={"q": q})
    assert response.status_code == 200, response.text
    return response.json()["hits"]


def test_a_review_is_found_by_what_it_says_wherever_it_says_it(client, provider):
    first = post_check(client).json()
    other = post_check(client, data={"subject": "ed"}).json()

    # Nothing but the transcription exists yet.
    assert find(client, "saturado") == [] and find(client, "despeja") == []

    ask_hint(client, first["id"])
    client.post(f"/api/checks/{first['id']}/level/2", headers=AUTH)
    hits = find(client, "division")  # typed without the accent
    assert [h["check_id"] for h in hits] == [first["id"]]
    assert hits[0]["kinds"] == ["hint"] and hits[0]["subject"] == "general"
    marked = [part["text"] for part in hits[0]["snippet"] if part["hit"]]
    assert marked == ["división"]
    shown = "".join(p["text"] for p in hits[0]["snippet"])
    assert shown.startswith("Revisa la división del paso 3.")

    # The explanation is searchable too, by the start of a word, and every word must match.
    assert find(client, "ecuac lineal")[0]["kinds"] == ["explanation"]
    assert find(client, "lineal saturado") == []

    # The chat joins the index when the answer is complete.
    with client.stream(
        "POST", f"/api/checks/{other['id']}/chat", headers=AUTH, data={"message": "¿Y la raíz?"}
    ) as stream:
        "".join(stream.iter_text())
    assert [h["check_id"] for h in find(client, "raiz")] == [other["id"]]
    assert find(client, "raiz")[0]["kinds"] == ["chat"]


def test_search_follows_corrections_and_treats_the_query_as_plain_words(client, provider):
    first = post_check(client).json()
    # mkstep writes the SymPy text as LaTeX: the reading says "Eq(x, 4)".
    assert [h["check_id"] for h in find(client, "Eq 4")] == [first["id"]]

    provider.rebuilt = ("Eq(x, 3)", ["s2"])
    correct(client, first["id"], "s3", "x = 37")
    assert find(client, "37")[0]["kinds"] == ["steps"]

    # FTS5 operators and punctuation are just characters to us.
    for odd in ('"', "x AND", "NEAR(", "a* OR b", "\\frac{1}{s}", "col:x"):
        assert client.get("/api/search", headers=AUTH, params={"q": odd}).status_code in (200, 422)
    assert client.get("/api/search", headers=AUTH, params={"q": "  ¿? "}).status_code == 422
    assert client.get("/api/search", headers=AUTH, params={"q": "x" * 201}).status_code == 422
    assert client.get("/api/search", params={"q": "x"}).status_code == 401


def test_reviews_made_before_the_index_existed_are_indexed_at_startup(settings, provider):
    from sqlalchemy import text

    client = TestClient(create_app(settings, provider))
    first = post_check(client).json()
    with Session(make_engine(settings.resolved_database_url)) as db:
        db.connection().execute(text("DELETE FROM search_index"))
        db.commit()
    assert find(client, "Eq") == []

    restarted = TestClient(create_app(settings, provider))

    assert [h["check_id"] for h in find(restarted, "Eq")] == [first["id"]]


def test_a_review_can_be_read_back_by_a_device_without_a_copy(client, provider):
    first = post_check(client).json()
    ask_hint(client, first["id"])
    calls = provider.calls

    body = client.get(f"/api/checks/{first['id']}", headers=AUTH).json()

    assert body["id"] == first["id"] and body["hint"]["step_id"] == "s3"
    assert body["cost_usd"] == 0 and provider.calls == calls
    assert client.get("/api/checks/nope", headers=AUTH).status_code == 404
    assert client.get(f"/api/checks/{first['id']}").status_code == 401


# --- graphing (4e) ------------------------------------------------------------


def post_plot(client, **overrides):
    request = {
        "headers": AUTH,
        "data": {"subject": "general"},
        "files": {"image": ("selection.png", png(), "image/png")},
    }
    request.update(overrides)
    return client.post("/api/plot", **request)


def test_a_selected_equation_comes_back_as_something_to_draw(client, settings, provider):
    provider.page = page([("s1", "Eq(y, x**2 - 4)", R.GIVEN, ())])

    response = post_plot(client)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["plottable"] is True and (body["label"], body["variable"]) == ("y", "x")
    assert body["tree"]["op"] == "+"
    # Reading costs like a review and is charged; nothing else is kept on the server.
    assert body["cost_usd"] == 0.05 and body["usage"]["checks_this_month"] == 0
    assert list((settings.data_dir / "images").iterdir()) == []
    with Session(make_engine(settings.resolved_database_url)) as db:
        assert [u.endpoint for u in db.exec(select(UsageLog)).all()] == ["plot"]


def test_an_equation_that_cannot_be_drawn_says_why_and_still_reports_its_cost(client, provider):
    # The default page solves 2x + 4 = 10 down to "x = 4": equations and a value, no y = f(x).
    body = post_plot(client).json()

    assert body["plottable"] is False and "no está despejada" in body["reason"]
    assert body["tree"] is None and body["cost_usd"] == 0.05


def test_plotting_respects_token_budget_and_bad_uploads(client, settings, provider):
    assert client.post("/api/plot", data={"subject": "general"}).status_code == 401
    assert post_plot(client, data={"subject": "nope"}).status_code == 404
    bad = post_plot(client, files={"image": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 400 and provider.calls == 0
    with Session(make_engine(settings.resolved_database_url)) as db:
        db.add(UsageLog(endpoint="check", model="m", cost_usd=5.0))
        db.commit()
    assert post_plot(client).status_code == 402 and provider.calls == 0


# --- notebook backups (phase 5) -----------------------------------------------

NOTEBOOK = "0b8f6c1e-2a47-4c5d-9e3f-1a2b3c4d5e6f"


def exported(notebook_id=NOTEBOOK, strokes=2, title="Tarea 3"):
    stroke = {"format_version": 1, "id": "s", "tool": "pen", "points": [[1, 2, 0.5]]}
    return {
        "format": "paso-notebook",
        "format_version": 1,
        "exported_at": "2026-11-15T10:00:00Z",
        "subject": {"name": "Ecuaciones Diferenciales", "slug": "ed", "template": "ed", "tags": []},
        "notebook": {"id": notebook_id, "subject_id": "sub", "title": title, "position": 0},
        "pages": [{"page": {"id": "p1", "background": "grid"}, "strokes": [stroke] * strokes}],
    }


def put_notebook(client, body=None, notebook_id=NOTEBOOK, **params):
    return client.put(
        f"/api/notebooks/{notebook_id}", headers=AUTH, json=body or exported(), params=params
    )


def test_a_notebook_is_kept_as_the_file_the_app_exports(client, settings):
    response = put_notebook(client, semester="2026-2")
    assert response.status_code == 200, response.text
    card = response.json()

    assert (card["title"], card["subject_name"], card["semester_name"]) == (
        "Tarea 3",
        "Ecuaciones Diferenciales",
        "2026-2",
    )
    assert (card["pages"], card["strokes"]) == (1, 2) and card["size_bytes"] > 0
    listed = client.get("/api/notebooks", headers=AUTH).json()["notebooks"]
    assert listed == [card]
    # What comes back is what went in, and the file on disk is a plain export.
    assert client.get(f"/api/notebooks/{NOTEBOOK}", headers=AUTH).json() == exported()
    on_disk = settings.data_dir / "notebooks" / f"{NOTEBOOK}.paso.json"
    assert '"format":"paso-notebook"' in on_disk.read_text(encoding="utf-8")


def test_a_new_upload_replaces_the_copy_and_keeps_the_one_before(client, settings):
    put_notebook(client, exported(strokes=5))
    put_notebook(client, exported(strokes=1, title="Tarea 3 (corregida)"))

    card = client.get("/api/notebooks", headers=AUTH).json()["notebooks"][0]
    assert (card["title"], card["strokes"]) == ("Tarea 3 (corregida)", 1)
    folder = settings.data_dir / "notebooks"
    # One step back survives on disk, in case the upload was a mistake.
    assert len((folder / f"{NOTEBOOK}.paso.prev").read_text(encoding="utf-8")) > len(
        (folder / f"{NOTEBOOK}.paso.json").read_text(encoding="utf-8")
    )
    assert not list(folder.glob("*.tmp"))


def test_bad_uploads_are_refused_and_never_reach_the_disk(client, settings):
    assert put_notebook(client, {"format": "something-else", "pages": []}).status_code == 422
    assert put_notebook(client, exported(notebook_id="another")).status_code == 422
    broken = exported()
    broken["pages"] = [{"page": {}}]
    assert put_notebook(client, broken).status_code == 422
    # An id that is not one of ours never becomes a path.
    for odd in ("..%2F..%2Fetc", "x", "0b8f6c1e-2a47-4c5d-9e3f-1a2b3c4d5e6f.json"):
        assert client.get(f"/api/notebooks/{odd}", headers=AUTH).status_code == 404
        assert client.put(
            f"/api/notebooks/{odd}", headers=AUTH, json=exported(odd)
        ).status_code in (
            404,
            422,
        )
    assert list((settings.data_dir / "notebooks").iterdir()) == []
    for call in (
        lambda: client.get("/api/notebooks"),
        lambda: client.get(f"/api/notebooks/{NOTEBOOK}"),
        lambda: client.put(f"/api/notebooks/{NOTEBOOK}", json=exported()),
        lambda: client.delete(f"/api/notebooks/{NOTEBOOK}"),
    ):
        assert call().status_code == 401


def test_the_server_copy_is_only_dropped_when_asked(client, settings):
    put_notebook(client)
    put_notebook(client)
    assert client.get(f"/api/notebooks/{NOTEBOOK}", headers=AUTH).status_code == 200

    assert client.delete(f"/api/notebooks/{NOTEBOOK}", headers=AUTH).json() == {"ok": True}

    assert client.get(f"/api/notebooks/{NOTEBOOK}", headers=AUTH).status_code == 404
    assert client.get("/api/notebooks", headers=AUTH).json() == {"notebooks": []}
    assert list((settings.data_dir / "notebooks").iterdir()) == []
    assert client.delete(f"/api/notebooks/{NOTEBOOK}", headers=AUTH).status_code == 404


def test_the_browser_may_upload_with_put(client):
    allowed = client.options(
        f"/api/notebooks/{NOTEBOOK}",
        headers={
            "Origin": "https://paso-libreta.paso-frontend.workers.dev",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert allowed.status_code == 200 and "PUT" in allowed.headers["access-control-allow-methods"]


def test_a_server_with_backups_on_makes_one_at_startup_and_reports_it(settings, provider):
    import time

    on = settings.model_copy(update={"backup_enabled": True})
    with TestClient(create_app(on, provider)) as live:
        post_check(live)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = live.get("/api/backup/status", headers=AUTH).json()
            if state["at"]:
                break
            time.sleep(0.1)

    assert state["enabled"] is True and state["ok"] is True
    # No external storage configured: it works, and it does not pretend otherwise.
    assert state["offsite"] is False and "solo en este servidor" in state["detail"]
    assert len(list(on.resolved_backup_dir.glob("paso-*.tar.gz"))) == 1


def test_a_laptop_makes_no_backups_and_says_so(client, settings):
    state = client.get("/api/backup/status", headers=AUTH).json()

    assert state == {"enabled": False, "offsite": False, "ok": None, "at": None, "detail": ""}
    assert not settings.resolved_backup_dir.exists()
    assert client.get("/api/backup/status").status_code == 401


def test_the_host_can_check_the_process_is_up_without_the_token(settings, provider):
    # Even a server with no token configured answers the ping, and only the ping.
    bare = TestClient(create_app(settings.model_copy(update={"app_token": ""}), provider))
    assert bare.get("/api/ping").json() == {"ok": True}
    assert bare.get("/api/health").status_code == 503
