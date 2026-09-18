"""Anthropic adapter (ADR 0005).

Everything provider-specific is confined here: vision input, structured
outputs, prompt caching, token accounting. `recognition/` and `verification/`
never import anthropic.
"""

from __future__ import annotations

import base64
import time

import anthropic

from app.llm.base import (
    LLMProvider,
    PreparedImage,
    PromptSpec,
    ProviderError,
    ProviderResult,
)
from app.llm.schema import RecognitionPayload
from app.llm.usage import estimate_cost
from app.schemas import Usage

#: Generous enough for a full page of steps; recognition output is JSON, not prose.
MAX_OUTPUT_TOKENS = 8000


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        client: anthropic.Anthropic | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        # A bare Anthropic() also resolves an `ant auth login` profile, so an
        # unset ANTHROPIC_API_KEY does not necessarily mean no credentials.
        self._client = client or anthropic.Anthropic(
            **({"api_key": api_key} if api_key else {}),
            timeout=timeout,
        )

    def extract_steps(
        self,
        image: PreparedImage,
        system_prompt: PromptSpec,
        instruction: str,
    ) -> ProviderResult:
        started = time.perf_counter()

        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt.text,
                        # The system prompt and the subject's notation notes are
                        # identical across every review of the same subject, so
                        # caching them takes a real bite out of the per-call cost
                        # and latency (D4, D5).
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": image.media_type,
                                    "data": base64.standard_b64encode(image.data).decode(),
                                },
                            },
                            {"type": "text", "text": instruction},
                        ],
                    }
                ],
                output_format=RecognitionPayload,
            )
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"El API respondió {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"No se pudo conectar con el API: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        warnings: list[str] = []

        # Check why generation stopped before trusting the content.
        if response.stop_reason == "max_tokens":
            raise ProviderError(
                "La respuesta se truncó por max_tokens. Selecciona una región más "
                "pequeña o sube MAX_OUTPUT_TOKENS."
            )
        if response.stop_reason == "refusal":
            raise ProviderError("El modelo declinó procesar esta imagen.")

        payload = response.parsed_output
        if payload is None:
            raise ProviderError("El modelo no devolvió una transcripción utilizable.")

        return ProviderResult(
            steps=[step.to_step() for step in payload.steps],
            usage=self._usage_of(response, latency_ms),
            warnings=warnings,
        )

    # --- internals --------------------------------------------------------

    def _usage_of(self, response: object, latency_ms: int) -> Usage:
        raw = getattr(response, "usage", None)
        input_tokens = int(getattr(raw, "input_tokens", 0) or 0)
        output_tokens = int(getattr(raw, "output_tokens", 0) or 0)
        cache_write = int(getattr(raw, "cache_creation_input_tokens", 0) or 0)
        cache_read = int(getattr(raw, "cache_read_input_tokens", 0) or 0)

        return Usage(
            endpoint="recognize",
            model=self.model,
            # Cached tokens are still input tokens; keeping them in the total
            # makes the usage log comparable across cache hits and misses.
            input_tokens=input_tokens + cache_write + cache_read,
            output_tokens=output_tokens,
            cost_usd=estimate_cost(
                self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_write_tokens=cache_write,
                cache_read_tokens=cache_read,
            ),
            latency_ms=latency_ms,
        )
