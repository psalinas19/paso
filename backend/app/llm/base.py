"""The provider boundary (SPEC 12.3, D8).

The interface is "give me the steps in this image, conforming to this schema",
not "call the API". Anything provider-specific -- structured outputs, tool use,
whatever a future SDK calls it -- lives inside the adapter, so swapping models
or vendors does not touch recognition, verification or the CLIs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.schemas import ImageMeta, Step, Usage


@dataclass(frozen=True)
class PreparedImage:
    """An image already resized and encoded, ready to send."""

    data: bytes
    media_type: str
    width: int
    height: int
    source_path: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def to_meta(self) -> ImageMeta:
        return ImageMeta(
            sha256=self.sha256,
            media_type=self.media_type,
            width=self.width,
            height=self.height,
            bytes_sent=len(self.data),
            source_path=self.source_path,
        )


@dataclass(frozen=True)
class PromptSpec:
    """A prompt plus its identity.

    `version` is the hash of the file, not a hand-maintained string, so a prompt
    edit can never go untracked in the eval history (SPEC 12.3).
    """

    text: str
    version: str
    path: str | None = None

    @classmethod
    def from_file(cls, path: Path, **substitutions: str) -> PromptSpec:
        """Load a prompt and fill in its {placeholders}.

        Plain replacement rather than str.format, because a prompt is prose that
        may well end up containing a literal brace -- a LaTeX snippet, a code
        example -- and format() would raise on it.

        The version hashes the file *before* substitution, so it identifies the
        prompt itself; the subject is recorded separately.
        """
        raw = path.read_text(encoding="utf-8")
        version = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        text = raw
        for key, value in substitutions.items():
            text = text.replace("{" + key + "}", value)
        return cls(text=text, version=version, path=str(path))


@dataclass
class ProviderResult:
    steps: list[Step]
    usage: Usage
    warnings: list[str] = field(default_factory=list)


class ProviderError(RuntimeError):
    """The provider could not produce a usable result."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    def extract_steps(
        self,
        image: PreparedImage,
        system_prompt: PromptSpec,
        instruction: str,
    ) -> ProviderResult:
        """Read the image and return the steps written in it."""
        ...
