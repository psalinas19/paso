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


def test_explaining_and_solving_are_structured_calls_with_their_own_schemas():
    from app.llm.schema import ExplanationPayload, NotePayload, SolutionPayload, SolvedStep

    explanation = ExplanationPayload(
        overview="Lineal.",
        notes=[NotePayload(step_id="s2", note="Restaste 2.")],
        suspect_step_id=None,
        corrected_latex="x = 3",
        corrected_sympy="Eq(x, 3)",
        next_step="",
        takeaway="Lo mismo en ambos lados.",
    )
    provider, messages = provider_with(explanation)
    draft = provider.explain(PROMPT, "the instruction", None)
    assert draft.notes == [("s2", "Restaste 2.")] and draft.corrected_sympy == "Eq(x, 3)"
    assert draft.usage.endpoint == "explain"
    assert messages.request["output_format"] is ExplanationPayload

    solved = SolutionPayload(
        goal="Despejar x.",
        method="Inversas.",
        steps=[
            SolvedStep(
                id="r1",
                latex="x = 3",
                sympy="Eq(x, 3)",
                kind="equation",
                relation="result",
                derives_from=["g1"],
                why="Dividiendo entre 2.",
            )
        ],
        answer="$x = 3$",
        check="",
    )
    provider, messages = provider_with(solved)
    image = PreparedImage(data=b"png", media_type="image/png", width=1, height=1)
    draft = provider.solve(PROMPT, "the instruction", image)
    assert [(s.id, s.sympy, s.derives_from) for s in draft.steps] == [("r1", "Eq(x, 3)", ["g1"])]
    assert draft.whys == {"r1": "Dividiendo entre 2."} and draft.usage.endpoint == "solve"
    assert [b["type"] for b in messages.request["messages"][0]["content"]] == ["image", "text"]
    assert messages.request["output_format"] is SolutionPayload


def test_effort_is_sent_only_when_configured():
    payload = HintPayload(step_id=None, error_type=None, hint="")
    messages = FakeMessages(payload)
    client = SimpleNamespace(messages=messages)

    AnthropicProvider("claude-sonnet-5-5", client=client).write_hint(PROMPT, "x", None)
    assert "output_config" not in messages.request

    AnthropicProvider("claude-sonnet-5-5", client=client, effort="low").write_hint(
        PROMPT, "x", None
    )
    assert messages.request["output_config"] == {"effort": "low"}
    assert messages.request["output_format"] is HintPayload  # the schema still travels


class FakeStream:
    """Stands in for client.messages.stream(...): a context manager with the
    text as it arrives and the final message once it is done."""

    def __init__(self, pieces, stop_reason="end_turn"):
        self.text_stream = iter(pieces)
        self._stop_reason = stop_reason
        self.request: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return SimpleNamespace(
            stop_reason=self._stop_reason,
            usage=SimpleNamespace(
                input_tokens=2000,
                output_tokens=300,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )


def chat_with(stream, **options):
    from app.llm.base import ChatTurn
    from app.schemas import Usage

    def start(**request):
        stream.request = request
        return stream

    client = SimpleNamespace(messages=SimpleNamespace(stream=start))
    provider = AnthropicProvider("claude-sonnet-5-5", client=client, **options)
    turns = [
        ChatTurn("user", "¿por qué?"),
        ChatTurn("assistant", "porque sí"),
        ChatTurn("user", "¿y?"),
    ]
    image = PreparedImage(data=b"png", media_type="image/png", width=1, height=1)
    out = list(provider.chat(PROMPT, "estado del ejercicio", turns, image))
    return [p for p in out if isinstance(p, str)], [p for p in out if isinstance(p, Usage)]


def test_chat_streams_text_then_reports_its_cost():
    stream = FakeStream(["Hola, ", "mira el paso 3."])
    text, usage = chat_with(stream, chat_model="claude-haiku-5-5", effort="low")

    assert text == ["Hola, ", "mira el paso 3."]
    assert len(usage) == 1 and usage[0].endpoint == "chat" and usage[0].cost_usd > 0
    assert usage[0].model == "claude-haiku-5-5"  # priced as the model that answered
    request = stream.request
    assert request["model"] == "claude-haiku-5-5"
    # The rules are cached; the state of the exercise travels after them, uncached.
    assert request["system"][0]["text"] == "system text" and "cache_control" in request["system"][0]
    assert request["system"][1] == {"type": "text", "text": "estado del ejercicio"}
    # The ink goes with the first question only.
    kinds = [[block["type"] for block in m["content"]] for m in request["messages"]]
    assert kinds == [["image", "text"], ["text"], ["text"]]
    assert request["output_config"] == {"effort": "low"}


def test_chat_uses_the_main_model_unless_another_is_configured():
    stream = FakeStream(["ok"])
    chat_with(stream)
    assert stream.request["model"] == "claude-sonnet-5-5"
    assert "output_config" not in stream.request


def test_a_cut_off_or_refused_chat_answer_says_so():
    text, usage = chat_with(FakeStream(["a medias"], stop_reason="max_tokens"))
    assert "se cortó" in text[-1] and len(usage) == 1
    with pytest.raises(ProviderError):
        chat_with(FakeStream(["no"], stop_reason="refusal"))
