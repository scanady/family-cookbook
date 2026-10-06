"""Which service a model name reaches, and what the engine makes of OpenRouter's
answers: the parsed result, the cost it reports, retries, refusals, and the
route that can draw a 4K photo. OpenRouter is stood in for; nothing here
calls a real model."""
import base64
import io
import json
import urllib.error

import pytest

from family_cookbook import models


@pytest.fixture
def keys(monkeypatch):
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return lambda **env: [monkeypatch.setenv(k, v) for k, v in env.items()]


class FakeOpenRouter:
    """Answers each request with the next canned reply: a dict is a 200 body, an
    int an HTTP error with that status."""

    def __init__(self, monkeypatch, *replies):
        self.replies = list(replies)
        self.requests: list[dict] = []
        monkeypatch.setattr(models.urllib.request, "urlopen", self.urlopen)
        monkeypatch.setattr(models, "RETRY_WAIT_S", 0)

    def urlopen(self, request, timeout):
        self.requests.append({"url": request.full_url, "body": json.loads(request.data)})
        reply = self.replies.pop(0)
        if isinstance(reply, int):
            raise urllib.error.HTTPError(request.full_url, reply, "error", {},
                                         io.BytesIO(json.dumps({"error": {"message": "nope"}}).encode()))
        return io.BytesIO(json.dumps(reply).encode())


def chat(content, cost=0.0021):
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1200, "completion_tokens": 300, "cost": cost}}


def test_a_gemini_key_wins_and_openrouter_serves_the_same_model_without_one(keys):
    keys(OPENROUTER_API_KEY="sk-or-test")
    assert isinstance(models.load("gemini-3.8-flash"), models.OpenRouter)
    assert models.load("gemini-3.8-flash").name == "google/gemini-3.8-flash"
    keys(GEMINI_API_KEY="gemini-test")
    assert isinstance(models.load("gemini-3.8-flash"), models.Gemini)
    assert models.load("anthropic/claude-sonnet").name == "anthropic/claude-sonnet"


def test_no_key_means_ai_is_off(keys):
    assert models.service() is None
    with pytest.raises(SystemExit):
        models.load("gemini-3.8-flash")


def test_an_answer_comes_back_parsed_with_the_cost_openrouter_reports(keys, monkeypatch, tmp_path):
    keys(OPENROUTER_API_KEY="sk-or-test")
    page = tmp_path / "card.jpg"
    page.write_bytes(b"\xff\xd8 jpeg")
    fake = FakeOpenRouter(monkeypatch, 429, chat('{"title": "Pop-overs"}'))
    answer, usage = models.load("gemini-3.8-flash").json("read it", {"type": "object"}, [page])
    assert answer == {"title": "Pop-overs"}
    assert usage == models.Usage(1200, 300, 0.0021)
    assert len(fake.requests) == 2  # the rate limit was waited out
    sent = fake.requests[-1]["body"]
    assert sent["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert sent["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_an_empty_answer_is_a_refusal_the_caller_can_skip(keys, monkeypatch):
    keys(OPENROUTER_API_KEY="sk-or-test")
    FakeOpenRouter(monkeypatch, chat(None))
    with pytest.raises(models.Refused):
        models.load("gemini-3.8-flash").json("read it", {"type": "object"})


def test_a_heic_photo_is_refused_before_it_is_sent(keys, monkeypatch, tmp_path):
    keys(OPENROUTER_API_KEY="sk-or-test")
    page = tmp_path / "card.heic"
    page.write_bytes(b"heic")
    fake = FakeOpenRouter(monkeypatch)
    with pytest.raises(SystemExit, match="JPEG"):
        models.load("gemini-3.8-flash").json("read it", {"type": "object"}, [page])
    assert fake.requests == []


def test_a_4k_gemini_photo_goes_only_to_the_route_that_draws_4k(keys, monkeypatch):
    keys(OPENROUTER_API_KEY="sk-or-test")
    drawn = base64.b64encode(b"png bytes").decode()
    fake = FakeOpenRouter(monkeypatch, {"data": [{"b64_json": drawn}],
                                        "usage": {"prompt_tokens": 400, "completion_tokens": 2000, "cost": 0.24}})
    data, usage = models.load("gemini-3-pro-image").image("a pot of beans", "3:4", "4K")
    assert data == b"png bytes" and usage.cost_usd == 0.24
    body = fake.requests[0]["body"]
    assert fake.requests[0]["url"].endswith("/images")
    assert (body["aspect_ratio"], body["resolution"]) == ("3:4", "4K")
    assert body["provider"] == {"only": ["google-ai-studio"], "allow_fallbacks": False}


def test_an_empty_balance_says_where_to_add_credits(keys, monkeypatch):
    keys(OPENROUTER_API_KEY="sk-or-test")
    FakeOpenRouter(monkeypatch, 402)
    with pytest.raises(SystemExit, match="credits"):
        models.load("gemini-3.8-flash").json("read it", {"type": "object"})
