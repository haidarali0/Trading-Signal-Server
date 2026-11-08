from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError

import engine.llm as llm
from helper import utils


def test_openrouter_authentication_error_has_key_guidance(monkeypatch):
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(401, request=request)
    error = APIStatusError(
        "Authentication failed",
        response=response,
        body={"error": {"message": "User not found."}},
    )

    def fail_request(**_kwargs):
        raise error

    monkeypatch.setattr(
        llm,
        "OpenAI",
        lambda **_kwargs: SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=fail_request),
            ),
        ),
    )

    with pytest.raises(RuntimeError, match=r"\[OpenRouter\].*OPENROUTER_API_KEY"):
        llm.inference("{}", "BTCUSDT", "1h")


def test_openrouter_rejects_non_object_signal_response(monkeypatch):
    monkeypatch.setattr(
        llm,
        "OpenAI",
        lambda **_kwargs: SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content="0.72"),
                            ),
                        ],
                        usage=None,
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=r"\[OpenRouter\].*returned a float.*expected a JSON object signal",
    ):
        llm.inference("{}", "BTCUSDT", "1h")


def test_telegram_api_error_has_configuration_guidance(monkeypatch, tmp_path):
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(b"chart")
    response = SimpleNamespace(
        status_code=400,
        text='{"ok":false,"description":"Chat not found"}',
        json=lambda: {"ok": False, "description": "Chat not found"},
    )
    monkeypatch.setattr(utils.requests, "post", lambda *_args, **_kwargs: response)

    with pytest.raises(RuntimeError, match=r"\[Telegram\].*TELEGRAM_CHAT_ID.*Chat not found"):
        utils.send_telegram_message("test", str(image_path))
