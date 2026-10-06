"""The AI models behind `cookbook ingest` and `cookbook photo`, behind one interface.

A command asks for a model by name (`--model`), gets an object with `json()`
(and, for an image model, `image()`), and never touches a provider's API.
Two services reach the models: Google's Gemini API (GEMINI_API_KEY) and
OpenRouter (OPENROUTER_API_KEY), which serves the same Gemini models and many
others. `load()` picks the service from the model name and the keys set.

Every call returns its token usage and its cost: OpenRouter reports it, and a
Gemini model in PRICES is priced here. The commands append what each recipe
cost to book/sources/ai-log.jsonl, so a book's AI spend is on record.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
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


def gemini_key() -> str | None:
    """GEMINI_API_KEY or GOOGLE_API_KEY, as the SDK reads them. The CLI fills
    the environment from the book's .env first (config.load_env)."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None


def openrouter_key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY") or None


def service() -> str | None:
    """The service a Gemini model name goes to: Google when its key is set,
    else OpenRouter when that key is; None when AI is off."""
    if gemini_key():
        return "Gemini"
    if openrouter_key():
        return "OpenRouter"
    return None


# What every AI command says when there is no key, before it carries on without AI.
NO_KEY = ("AI is off: no AI key. In the book's .env file, paste a Gemini key "
          "(https://aistudio.google.com/apikey) after GEMINI_API_KEY=, or an OpenRouter key "
          "(https://openrouter.ai/keys) after OPENROUTER_API_KEY=.")


class Gemini:
    """Google's Gemini API through the google-genai SDK."""

    def __init__(self, name: str) -> None:
        from google import genai

        key = gemini_key()
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


OPENROUTER_API = "https://openrouter.ai/api/v1"
OPENROUTER_TIMEOUT_S = 300   # a 4K image takes a minute or two
OPENROUTER_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
OPENROUTER_TRANSIENT = {408, 429, 500, 502, 503, 504, 529}


class OpenRouter:
    """Any model on OpenRouter (https://openrouter.ai) through its HTTP API.
    `name` is OpenRouter's model id, such as google/gemini-3.8-flash."""

    def __init__(self, name: str) -> None:
        key = openrouter_key()
        if not key:
            raise SystemExit(f"{name} is an OpenRouter model: paste an OpenRouter key "
                             "(https://openrouter.ai/keys) after OPENROUTER_API_KEY= in the book's .env file")
        self.name = name
        self._key = key

    def _post(self, path: str, body: dict) -> dict:
        request = urllib.request.Request(
            OPENROUTER_API + path, data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json",
                     "HTTP-Referer": "https://github.com/scanady/family-cookbook", "X-Title": "family-cookbook"})
        wait = RETRY_WAIT_S
        for attempt in range(RETRIES + 1):
            try:
                with urllib.request.urlopen(request, timeout=OPENROUTER_TIMEOUT_S) as response:
                    data = json.load(response)
                error = data.get("error")
                if not error:
                    return data
                code, message = error.get("code"), error.get("message", "")
            except urllib.error.HTTPError as exc:
                try:
                    error = json.load(exc).get("error") or {}
                except ValueError:
                    error = {}
                code, message = exc.code, error.get("message") or exc.reason
            except (urllib.error.URLError, TimeoutError) as exc:
                code, message = None, str(getattr(exc, "reason", exc))
            if (code is None or code in OPENROUTER_TRANSIENT) and attempt < RETRIES:
                time.sleep(wait)
                wait *= 2
                continue
            if code == 401:
                raise SystemExit("the OpenRouter API key was rejected as not valid — check OPENROUTER_API_KEY "
                                 "in the book's .env file or your environment (keys: https://openrouter.ai/keys)")
            if code == 402:
                raise SystemExit("OpenRouter has no credits left on this key: add some at "
                                 "https://openrouter.ai/settings/credits")
            raise SystemExit(f"{self.name}: {code or 'no connection'}: {message}")

    def _usage(self, data: dict) -> Usage:
        u = data.get("usage") or {}
        tokens_in, tokens_out = u.get("prompt_tokens") or 0, u.get("completion_tokens") or 0
        reported = u.get("cost")
        price = cost(self.name.removeprefix("google/"), tokens_in, tokens_out)
        return Usage(tokens_in, tokens_out, float(reported) if reported is not None else price)

    def json(self, prompt: str, schema: dict, images: Sequence[Path] = ()) -> tuple[dict, Usage]:
        content: list[dict] = []
        for i, image in enumerate(images, 1):
            mime = mimetypes.guess_type(image.name)[0] or "image/jpeg"
            if mime not in OPENROUTER_IMAGE_TYPES:
                raise SystemExit(f"{image.name}: OpenRouter reads JPEG, PNG, WebP, and GIF pictures only — "
                                 "save it as a JPEG, or use a Gemini key")
            url = f"data:{mime};base64,{base64.b64encode(image.read_bytes()).decode()}"
            content += [{"type": "text", "text": f"Page {i}:"}, {"type": "image_url", "image_url": {"url": url}}]
        content.append({"type": "text", "text": prompt})
        data = self._post("/chat/completions", {
            "model": self.name,
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "answer", "strict": True, "schema": schema}},
            "temperature": 0,
            # Only an endpoint that honors response_format: the answer must match the schema.
            "provider": {"require_parameters": True},
        })
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content")
        if not text:
            raise Refused(f"{self.name} returned no answer ({choice.get('finish_reason') or 'no choices'})")
        return json.loads(text), self._usage(data)

    def image(self, prompt: str, aspect_ratio: str, size: str) -> tuple[bytes, Usage]:
        body: dict = {"model": self.name, "prompt": prompt, "aspect_ratio": aspect_ratio, "resolution": size}
        if self.name.startswith("google/") and size == "4K":
            # Google AI Studio draws Gemini images at 4K; Vertex, OpenRouter's
            # other route, stops at 2K, which prints soft.
            body["provider"] = {"only": ["google-ai-studio"], "allow_fallbacks": False}
        data = self._post("/images", body)
        drawn = (data.get("data") or [{}])[0].get("b64_json")
        if not drawn:
            raise SystemExit(f"{self.name} returned no image")
        return base64.b64decode(drawn), self._usage(data)


def load(name: str) -> Model:
    """A model by name. An OpenRouter id ("vendor/model") goes to OpenRouter. A
    Gemini name ("gemini-3.8-flash") goes to Google when GEMINI_API_KEY is set,
    else to OpenRouter as google/<name>, the same model."""
    if "/" in name:
        return OpenRouter(name)
    if not name.startswith("gemini-"):
        raise SystemExit(f"no service for model {name!r}: use a Gemini model (gemini-…) "
                         "or an OpenRouter model id (vendor/model)")
    if service() == "OpenRouter":
        return OpenRouter(f"google/{name}")
    return Gemini(name)
