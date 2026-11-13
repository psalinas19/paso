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
from app.llm.base import ProviderResult
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
