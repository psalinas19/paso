"""The Anthropic adapter's request shapes, against a fake client. No network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import PreparedImage, PromptSpec, ProviderError
from app.llm.schema import HintPayload, RecognizedStep

PROMPT = PromptSpec(text="system text", version="v1")


class FakeMessages:
    def __init__(self, parsed, stop_reason="end_turn"):
        self.parsed = parsed
        self.stop_reason = stop_reason
        self.request: dict = {}

    def parse(self, **request):
        self.request = request
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            parsed_output=self.parsed,
            usage=SimpleNamespace(
                input_tokens=1000,
                output_tokens=100,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )


def provider_with(parsed, stop_reason="end_turn"):
    messages = FakeMessages(parsed, stop_reason)
    client = SimpleNamespace(messages=messages)
    return AnthropicProvider("claude-sonnet-5-5", client=client), messages


def test_restructuring_is_a_text_only_structured_call():
    step = RecognizedStep(
        id="s3",
        latex="x = 3",
        sympy="Eq(x, 3)",
        kind="equation",
        relation="equivalent",
        derives_from=["s2"],
        confidence=0.9,
        legible=True,
        notes=None,
    )
    provider, messages = provider_with(step)

    result = provider.restructure_step(PROMPT, "the instruction")

    assert [s.sympy for s in result.steps] == ["Eq(x, 3)"]
    assert result.usage.endpoint == "correct" and result.usage.cost_usd > 0
    request = messages.request
    assert request["output_format"] is RecognizedStep
    assert request["messages"][0]["content"] == [{"type": "text", "text": "the instruction"}]
    assert request["system"][0]["text"] == "system text"


def test_a_hint_sends_the_ink_when_there_is_one():
    payload = HintPayload(step_id="s3", error_type="sign", hint="Revisa el signo.")
    provider, messages = provider_with(payload)
    image = PreparedImage(data=b"png-bytes", media_type="image/png", width=10, height=10)

    draft = provider.write_hint(PROMPT, "the instruction", image)

    assert (draft.step_id, draft.error_type, draft.hint) == ("s3", "sign", "Revisa el signo.")
    assert draft.usage.endpoint == "hint"
    kinds = [block["type"] for block in messages.request["messages"][0]["content"]]
    assert kinds == ["image", "text"]
    assert messages.request["output_format"] is HintPayload

    provider.write_hint(PROMPT, "the instruction", None)
    assert [b["type"] for b in messages.request["messages"][0]["content"]] == ["text"]


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_a_refused_or_truncated_answer_is_an_error_not_a_result(stop_reason):
    provider, _ = provider_with(None, stop_reason)
    with pytest.raises(ProviderError):
        provider.write_hint(PROMPT, "the instruction", None)
