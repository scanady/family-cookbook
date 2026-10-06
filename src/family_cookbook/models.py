"""The AI models behind `cookbook ingest` and `cookbook photo`, behind one interface.

A command asks for a model by name (`--model`), gets an object with `json()`
(and, for an image model, `image()`), and never touches a provider SDK. Adding
a provider is one class here and one entry in PROVIDERS; nothing else in the
engine changes.

Every call returns its token usage and, for a model in PRICES, its cost. The
commands append what each recipe cost to book/sources/ai-log.jsonl, so a
book's AI spend is on record.
"""
from __future__ import annotations

import datetime as dt
import json
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_IMAGE_MODEL = "gemini-3-pro-image"

# USD per 1M tokens: input, text output (thinking included), and for an image
# model, image output. Standard paid tier, from
# https://ai.google.dev/gemini-api/docs/pricing (October 2026). Gemini 3.8
# Flash's introductory price ends December 31, 2026, when it doubles to
# (1.50, 7.50). A model missing here still runs; its cost is logged as unknown.
PRICES: dict[str, tuple[float, ...]] = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3-pro-image": (2.00, 12.00, 120.00),      # a 4K image is 2,000 tokens, $0.24
    "gemini-3.1-flash-image": (0.50, 3.00, 60.00),    # a 4K image is 2,520 tokens, $0.151
}

RETRIES = 4           # transient failures (rate limit, overload) before giving up
RETRY_WAIT_S = 4.0    # first back-off; doubles each retry
LOG_NAME = "ai-log.jsonl"


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cost_usd: float | None  # None when the model's price is unknown

    def __add__(self, other: Usage) -> Usage:
        cost = None if self.cost_usd is None or other.cost_usd is None else self.cost_usd + other.cost_usd
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens, cost)

    def share(self, parts: int) -> Usage:
        """This usage split evenly across `parts` results of one call."""
        cost = None if self.cost_usd is None else self.cost_usd / parts
        return Usage(self.input_tokens // parts, self.output_tokens // parts, cost)

    def record(self) -> dict:
        cost = None if self.cost_usd is None else round(self.cost_usd, 5)
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "cost_usd": cost}


NO_USAGE = Usage(0, 0, 0.0)


class Refused(Exception):
    """The model returned nothing: a safety or recitation filter, most often.
    A caller can retry with less input or move on; one that cannot exits."""


def log(book: Path, record: dict) -> None:
    """Append one command's use for one entry to book/sources/ai-log.jsonl."""
    path = book / "sources" / LOG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"date": dt.datetime.now().isoformat(timespec="seconds"), **record},
                           ensure_ascii=False) + "\n")


class Model(Protocol):
    name: str

    def json(self, prompt: str, schema: dict, images: Sequence[Path] = ()) -> tuple[dict, Usage]:
        """Answer `prompt`, reading `images` in order, as an object matching the
        JSON Schema `schema`."""
        ...


class ImageModel(Protocol):
    name: str

    def image(self, prompt: str, aspect_ratio: str, size: str) -> tuple[bytes, Usage]:
        """One image for `prompt`, at `aspect_ratio` ("3:4") and `size` ("4K")."""
        ...


def cost(model: str, input_tokens: int, output_tokens: int, image_tokens: int = 0) -> float | None:
    price = PRICES.get(model)
    if price is None or (image_tokens and len(price) < 3):
        return None
    usd = input_tokens * price[0] + output_tokens * price[1] + (image_tokens * price[2] if image_tokens else 0)
    return usd / 1_000_000


def api_key() -> str | None:
    """The Gemini key from the environment, which the CLI fills from the book's
    .env (config.load_env). GEMINI_API_KEY or GOOGLE_API_KEY, as the SDK reads."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None


# What every AI command says when there is no key, before it carries on without AI.
NO_KEY = ("AI is off: no Gemini API key. Get one at https://aistudio.google.com/apikey and paste it "
          "after GEMINI_API_KEY= in the book's .env file.")


class Gemini:
    """Google's Gemini API through the google-genai SDK."""

    def __init__(self, name: str) -> None:
        from google import genai

        key = api_key()
        if not key:
            raise SystemExit(NO_KEY)
        self.name = name
        self._client = genai.Client(api_key=key)

    def _generate(self, contents: list, config):
        from google.genai import errors

        wait = RETRY_WAIT_S
        for attempt in range(RETRIES + 1):
            try:
                return self._client.models.generate_content(model=self.name, contents=contents, config=config)
            except (errors.ServerError, errors.ClientError) as exc:
                transient = isinstance(exc, errors.ServerError) or exc.code == 429
                if not transient or attempt == RETRIES:
                    if "API_KEY_INVALID" in str(exc):
                        raise SystemExit(
                            "the Gemini API key was rejected as not valid — check GEMINI_API_KEY in "
                            "the book's .env file or your environment (keys: https://aistudio.google.com/apikey)"
                        ) from None
                    raise SystemExit(f"{self.name}: {exc.code} {exc.status}: {exc.message}") from None
                time.sleep(wait)
                wait *= 2

    def json(self, prompt: str, schema: dict, images: Sequence[Path] = ()) -> tuple[dict, Usage]:
        from google.genai import types

        parts: list = []
        for i, image in enumerate(images, 1):
            mime = mimetypes.guess_type(image.name)[0] or "image/jpeg"
            parts += [f"Page {i}:", types.Part.from_bytes(data=image.read_bytes(), mime_type=mime)]
        parts.append(prompt)
        response = self._generate(parts, types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=schema,
            temperature=0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ))
        if not response.text:
            reason = response.candidates[0].finish_reason if response.candidates else "no candidates"
            raise Refused(f"{self.name} returned no answer ({reason})")
        meta = response.usage_metadata
        tokens_in = meta.prompt_token_count or 0
        tokens_out = (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
        return json.loads(response.text), Usage(tokens_in, tokens_out, cost(self.name, tokens_in, tokens_out))

    def image(self, prompt: str, aspect_ratio: str, size: str) -> tuple[bytes, Usage]:
        from google.genai import types

        response = self._generate([prompt], types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio, image_size=size),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ))
        data = next((p.inline_data.data for p in (response.parts or []) if p.inline_data is not None), None)
        if data is None:
            raise SystemExit(f"{self.name} returned no image: {(response.text or '').strip()[:200]}")
        meta = response.usage_metadata
        tokens_in = meta.prompt_token_count or 0
        thinking = meta.thoughts_token_count or 0
        image_tokens = meta.candidates_token_count or 0
        usage = Usage(tokens_in, thinking + image_tokens, cost(self.name, tokens_in, thinking, image_tokens))
        return data, usage


# Model-name prefix -> provider class.
PROVIDERS: dict[str, type] = {"gemini-": Gemini}


def load(name: str) -> Model:
    for prefix, provider in PROVIDERS.items():
        if name.startswith(prefix):
            return provider(name)
    known = ", ".join(f"{p}*" for p in PROVIDERS)
    raise SystemExit(f"no provider for model {name!r} — supported: {known}")
