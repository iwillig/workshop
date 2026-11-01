from workshop.agent.interactive import InteractiveAgent
from workshop.agent.default_agent import DefaultAgent


def test_interactive_output_is_concise_but_keeps_full_observation(
    monkeypatch, capsys
):
    class Model:
        def get_template_vars(self):
            return {}

        def format_observation_messages(self, message, outputs, template_vars):
            return [{"role": "user", "content": outputs[0]["output"]}]

    class Environment:
        def get_template_vars(self):
            return {}

        def execute(self, action):
            return {
                "output": "full file contents",
                "returncode": 0,
                "exception_info": "",
            }

    message = {
        "content": "Reading the file",
        "extra": {
            "actions": [{"tool": "read", "arguments": {"path": "a.py"}}]
        },
    }
    monkeypatch.setattr(DefaultAgent, "query", lambda self: message)
    agent = InteractiveAgent(Model(), Environment())
    agent.query()
    observations = agent.execute_actions(message)
    output = capsys.readouterr().out
    assert "read" in output
    assert "a.py" in output
    assert "full file contents" not in output
    assert observations[0]["content"] == "full file contents"


def test_interactive_final_response_is_not_printed_twice(monkeypatch, capsys):
    message = {
        "content": "Final findings",
        "extra": {"native_final": True, "actions": []},
    }
    monkeypatch.setattr(DefaultAgent, "query", lambda self: message)
    agent = InteractiveAgent(None, None)
    assert agent.query() == message
    assert "Final findings" not in capsys.readouterr().out
