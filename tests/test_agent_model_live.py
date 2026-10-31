"""Live LlmModel tests against the team's Hugging Face inference endpoint."""

import os

import pytest
from llm.default_plugins.openai_models import Chat

from workshop.agent.models import LlmModel


ENDPOINT = "https://ogabjrf7kkaavl1f.endpoints.huggingface.cloud/v1"
MODEL = "unsloth/Qwen3.8-27B-GGUF"


@pytest.fixture
def live_model(monkeypatch):
    token = os.environ.get("HF_TOKEN")
    if not token:
        pytest.fail("Set HF_TOKEN to run the live Hugging Face model tests.")
    backend = Chat(
        model_id="workshop-live-test", model_name=MODEL, api_base=ENDPOINT, key=token
    )
    monkeypatch.setattr("workshop.agent.models.llm.get_model", lambda _: backend)
    return LlmModel(model_name="workshop-live-test", retry_attempts=1)


def test_live_model_conversation(live_model):
    messages = [
        {
            "role": "system",
            "content": (
                "Reply with exactly one shell command in this exact format, "
                "using mswea_bash_command as the fence label, not bash:\n"
                "```mswea_bash_command\necho example\n```"
            ),
        },
        {"role": "user", "content": "Write a command that prints hello."},
    ]
    first = live_model.query(messages)
    assert first["role"] == "assistant"
    assert first["extra"]["actions"][0]["command"]
    assert first["extra"]["cost"] >= 0
    messages.extend(
        [first, {"role": "user", "content": "Now write a command that prints goodbye."}]
    )
    second = live_model.query(messages)
    assert second["extra"]["actions"][0]["command"]
    assert len(live_model._conversation.responses) == 2
