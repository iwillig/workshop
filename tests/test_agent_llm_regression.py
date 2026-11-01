from workshop.agent.default_agent import DefaultAgent
from workshop.agent.environments import LocalEnvironment
from workshop.agent.models import LlmModel


class Response:
    def __init__(self, content):
        self.content = content

    def text(self):
        return self.content

    def usage(self):
        return type("Usage", (), {"input": 0, "output": 0})()


class Conversation:
    def __init__(self):
        self.responses = []
        self.prompts = []

    def prompt(self, prompt, **kwargs):
        self.prompts.append(prompt)
        content = (
            "invalid response"
            if len(self.responses) == 0
            else (
                "```mswea_bash_command\n"
                "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```"
            )
        )
        response = Response(content)
        self.responses.append(response)
        return response


class Backend:
    def conversation(self):
        return Conversation()


def test_real_model_recovers_from_malformed_response(monkeypatch):
    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model", lambda _: Backend()
    )
    model = LlmModel(retry_attempts=1)
    agent = DefaultAgent(model, LocalEnvironment())
    result = agent.run("finish")
    assert result["exit_status"] == "Submitted"
    assert any(
        m["role"] == "assistant" and m["content"] == "invalid response"
        for m in agent.messages
    )
    assert "Format error" in model._conversation.prompts[1]
