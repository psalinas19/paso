"""Recognition wiring, with the provider faked. Never touches the network."""

from __future__ import annotations

import pytest
from PIL import Image

from app.config import Settings
from app.llm.base import PromptSpec, ProviderResult
from app.recognition.image import prepare_image
from app.recognition.service import build_prompt, recognize, repair_steps
from app.schemas import StepKind as K
from app.schemas import StepRelation as R
from app.schemas import Usage
from tests.conftest import mkstep


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, steps):
        self.steps = steps
        self.calls = 0
        self.last_prompt: PromptSpec | None = None

    def extract_steps(self, image, system_prompt, instruction):
        del image, instruction
        self.calls += 1
        self.last_prompt = system_prompt
        return ProviderResult(
            steps=list(self.steps),
            usage=Usage(endpoint="recognize", model=self.model, cost_usd=0.01),
        )


@pytest.fixture
def photo(tmp_path):
    path = tmp_path / "page.jpg"
    Image.new("RGB", (2400, 1600), "white").save(path)
    return path


@pytest.fixture
def settings(tmp_path):
    return Settings(
        anthropic_api_key="test",
        max_image_edge=1600,
        recognition_cache_enabled=False,
    )


# --- image preparation ------------------------------------------------------


def test_large_image_is_downscaled(photo):
    prepared = prepare_image(photo, max_edge=1600)
    assert max(prepared.width, prepared.height) == 1600
    assert prepared.media_type == "image/jpeg"
    assert prepared.data


def test_small_image_is_not_upscaled(tmp_path):
    path = tmp_path / "small.png"
    Image.new("RGB", (400, 300), "white").save(path)
    prepared = prepare_image(path, max_edge=1600)
    assert (prepared.width, prepared.height) == (400, 300)
    assert prepared.media_type == "image/png"


def test_missing_image_is_reported_clearly(tmp_path):
    with pytest.raises(FileNotFoundError):
        prepare_image(tmp_path / "nope.jpg", max_edge=1600)


# --- prompt assembly --------------------------------------------------------


def test_prompt_carries_subject_notation(circuitos):
    prompt = build_prompt(circuitos)
    assert "Circuitos Eléctricos I" in prompt.text
    assert "Hayt" in prompt.text
    assert "{subject_name}" not in prompt.text
    assert "{notation_notes}" not in prompt.text


def test_prompt_version_is_the_file_hash_not_the_subject(ed, circuitos):
    """Editing the prompt must change the version; changing subject must not."""
    assert build_prompt(ed).version == build_prompt(circuitos).version
    assert len(build_prompt(ed).version) == 12


# --- repairs ----------------------------------------------------------------


def test_dangling_parent_reference_is_dropped_not_fatal():
    steps = [
        mkstep("s1", "Eq(x, 1)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(x, 1)", K.EQUATION, R.EQUIVALENT, ("s99",)),
    ]
    repaired, warnings = repair_steps(steps)
    assert repaired[1].derives_from == ["s1"]  # dropped, then wired to previous
    assert any("s99" in w for w in warnings)


def test_forward_reference_is_dropped():
    """A step cannot derive from one written after it."""
    steps = [
        mkstep("s1", "Eq(x, 1)", K.EQUATION, R.EQUIVALENT, ("s2",)),
        mkstep("s2", "Eq(x, 1)", K.EQUATION, R.GIVEN),
    ]
    repaired, warnings = repair_steps(steps)
    assert repaired[0].derives_from == []
    assert warnings


def test_given_with_a_parent_is_cleaned():
    steps = [
        mkstep("s1", "Eq(x, 1)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(y, 2)", K.EQUATION, R.GIVEN, ("s1",)),
    ]
    repaired, warnings = repair_steps(steps)
    assert repaired[1].derives_from == []
    assert any("dato" in w for w in warnings)


def test_missing_parent_is_wired_to_the_previous_step():
    steps = [
        mkstep("s1", "Eq(2*x, 4)", K.EQUATION, R.GIVEN),
        mkstep("s2", "Eq(x, 2)", K.EQUATION, R.EQUIVALENT),
    ]
    repaired, warnings = repair_steps(steps)
    assert repaired[1].derives_from == ["s1"]
    assert any("enlacé" in w for w in warnings)


def test_assertion_without_a_parent_is_left_alone():
    """Sibling KCL equations legitimately have no parent (ADR 0003)."""
    steps = [
        mkstep("s1", "Eq(I_1 + I_2, 0)", K.EQUATION, R.ASSERTION),
        mkstep("s2", "Eq(I_2 + I_3, 0)", K.EQUATION, R.ASSERTION),
    ]
    repaired, warnings = repair_steps(steps)
    assert repaired[1].derives_from == []
    assert not warnings


# --- end to end with a fake provider ---------------------------------------


def test_recognize_returns_provenance(photo, ed, settings):
    provider = FakeProvider([mkstep("s1", "Eq(x, 1)", K.EQUATION, R.GIVEN)])
    result = recognize(photo, ed, provider, settings=settings)

    assert result.subject == "ed"
    assert result.model == "fake-model"
    assert result.prompt_version
    assert result.image is not None
    assert result.image.bytes_sent > 0
    assert result.usage is not None


def test_cache_prevents_a_second_paid_call(photo, ed, tmp_path, monkeypatch):
    """The whole point of the cache: iterating on the verifier is free."""
    monkeypatch.setattr("app.recognition.cache.CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr("app.llm.usage.USAGE_LOG", tmp_path / "usage.jsonl")

    cached_settings = Settings(
        anthropic_api_key="test", max_image_edge=1600, recognition_cache_enabled=True
    )
    provider = FakeProvider([mkstep("s1", "Eq(x, 1)", K.EQUATION, R.GIVEN)])

    first = recognize(photo, ed, provider, settings=cached_settings)
    second = recognize(photo, ed, provider, settings=cached_settings)

    assert provider.calls == 1
    assert second.usage.cache_hit is True
    assert [s.id for s in second.steps] == [s.id for s in first.steps]


def test_cache_only_refuses_instead_of_paying(photo, ed, settings, tmp_path, monkeypatch):
    monkeypatch.setattr("app.recognition.cache.CACHE_DIR", tmp_path / "cache")
    provider = FakeProvider([])
    with pytest.raises(LookupError, match="--no-llm|caché"):
        recognize(photo, ed, provider, settings=settings, cache_only=True)
    assert provider.calls == 0
