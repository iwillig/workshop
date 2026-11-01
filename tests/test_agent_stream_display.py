from types import SimpleNamespace

from llm.parts import StreamEvent

from workshop.agent.models import LlmModel


class StreamingResponse:
    def __init__(self, events):
        self.events = events
        self.streamed = False

    def stream_events(self):
        self.streamed = True
        yield from self.events

    def text(self):
        return "".join(event.chunk for event in self.events if event.type == "text")

    def tool_calls(self):
        return []

    def usage(self):
        return SimpleNamespace(input=5, output=3)


class Conversation:
    def __init__(self, response):
        self.response = response
        self.responses = []

    def prompt(self, prompt, **kwargs):
        response = self.response
        original = response.stream_events

        def stream():
            yield from original()
            self.responses.append(response)

        response.stream_events = stream
        return response


class Backend:
    def __init__(self, response):
        self.response = response

    def conversation(self):
        return Conversation(self.response)


def test_stream_prefers_reasoning_and_preserves_final_response(monkeypatch):
    response = StreamingResponse(
        [
            StreamEvent(type="reasoning", chunk="First thought."),
            StreamEvent(type="text", chunk="Final response."),
        ]
    )
    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model", lambda _: Backend(response)
    )
    model = LlmModel(protocol="native", retry_attempts=1)
    updates = []
    model.stream_callback = lambda source, text: updates.append((source, text))
    result = model.query([{"role": "user", "content": "task"}])
    assert response.streamed
    assert ("reasoning", "First thought.") in updates
    assert updates[-1] == ("reasoning", "First thought.")
    assert result["content"] == "Final response."


def test_interactive_agent_forwards_stream_to_progress(monkeypatch):
    from workshop.agent.interactive import InteractiveAgent

    response = StreamingResponse(
        [
            StreamEvent(type="reasoning", chunk="Inspecting code"),
            StreamEvent(type="text", chunk="done"),
        ]
    )
    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model", lambda _: Backend(response)
    )
    model = LlmModel(protocol="native", retry_attempts=1)
    agent = InteractiveAgent(model, None)
    agent.messages = [{"role": "user", "content": "task"}]
    events = []
    agent.progress_sink = events.append
    agent.query()
    assert any(
        event.startswith("[model:reasoning] ") and "Inspecting code" in event
        for event in events
    )
    assert not any("reset" in event for event in events)
    assert model.stream_callback is None


def test_stream_falls_back_to_bounded_latest_response(monkeypatch):
    response = StreamingResponse([StreamEvent(type="text", chunk="x" * 3000 + "END")])
    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model", lambda _: Backend(response)
    )
    model = LlmModel(protocol="native", retry_attempts=1)
    updates = []
    model.stream_callback = lambda source, text: updates.append((source, text))
    result = model.query([{"role": "user", "content": "task"}])
    assert updates[-1][0] == "response"
    assert updates[-1][1].endswith("END")
    assert len(updates[-1][1]) <= 1000
    assert len(result["content"]) == 3003
