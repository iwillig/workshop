import json

import pytest
from click.testing import CliRunner

from workshop.agent_eval.proposals import (
    load_proposals,
    record_proposal,
    record_proposal_decision,
    record_trace_review,
)
from workshop.agent_eval.review_runner import (
    local_only_environment,
    review_trace,
    truncate_trace,
    validate_reviewer_config,
)
from workshop.agent_eval.storage import PrivateStorage
from workshop.agent_benchmark.local import run_suite
from workshop.cli import cli


def captured_run(root, monkeypatch):
    class SavingAgent:
        progress_sink = None

        def run(self, inner_task):
            self.task = inner_task
            return {"exit_status": "Submitted", "submission": "done"}

        def save(self, path, *extra):
            return {"messages": [{"role": "user", "content": self.task}]}

    monkeypatch.setattr(
        "workshop.agent_config.build_agent", lambda config: SavingAgent()
    )
    return run_suite(
        "review-v1", {}, "reviewer", root, local=True, capture_trace=True
    )


def reviewer_config():
    return {
        "model": {
            "model_name": "local-reviewer",
            "protocol": "native",
            "retry_attempts": 1,
        },
    }


def fake_reviewer(content=None, record=None):
    import workshop.agent_eval.review_runner as runner

    content = content or json.dumps(
        {"observations": ["The agent read the file before reporting."]}
    )

    class FakeReviewer:
        messages = None

        def format_message(self, **kwargs):
            return dict(kwargs)

        def query(self, messages):
            self.messages = messages
            if record is not None:
                record.append(messages)
            return runner.review_model_message(content)

    return FakeReviewer()


class ReviewBackend:
    api_base = "http://127.0.0.1:19931/v1"

    def __init__(self, content=None):
        self.content = content or json.dumps(
            {"observations": ["The agent read the file before reporting."]}
        )

    def conversation(self):
        return self

    def prompt(self, prompt, **kwargs):
        return self

    def text(self):
        return self.content

    def tool_calls(self):
        return []

    def usage(self):
        return type("Usage", (), {"input": 0, "output": 0})()


@pytest.mark.parametrize(
    "changes",
    [
        {"model": {"model_name": "hf-glm"}},
        {"model": {"model_name": "local", "protocol": "shell"}},
        {"tools": {"read": {}}},
        {"mcp_servers": {"x": {}}},
        {"model": {}},
    ],
)
def test_reviewer_config_rejects_remote_or_toolful(changes):
    config = reviewer_config()
    config.update(changes)
    with pytest.raises(ValueError):
        validate_reviewer_config(config)


def test_reviewer_config_requires_loopback(monkeypatch):
    import workshop.agent_eval.review_runner as runner

    monkeypatch.setattr(
        runner,
        "resolve_llm_model",
        lambda name: type(
            "M", (), {"api_base": "https://remote.example/v1"}
        )(),
    )
    with pytest.raises(ValueError, match="loopback"):
        validate_reviewer_config(reviewer_config())


def test_truncate_keeps_tail_and_records_budget():
    record = {
        "cases": [
            {
                "trajectory": {
                    "messages": [
                        {"role": "user", "content": "x" * 3000},
                        {"role": "assistant", "content": "FINAL"},
                    ]
                }
            }
        ]
    }
    text, dropped, truncated = truncate_trace(record, 200)
    assert truncated is True and dropped > 0
    assert "FINAL" in text
    assert len(text) <= 260


def test_short_trace_is_not_truncated():
    record = {"cases": []}
    text, dropped, truncated = truncate_trace(record, 1000)
    assert (dropped, truncated) == (0, False)


def test_review_links_trace_and_stores_observations(tmp_path, monkeypatch):
    import workshop.agent_eval.review_runner as runner

    root = tmp_path / "private"
    report = captured_run(root, monkeypatch)
    reference = report["run"]["trace"]
    monkeypatch.setattr(
        runner,
        "resolve_llm_model",
        lambda name: ReviewBackend(),
    )
    monkeypatch.setattr(
        runner, "build_reviewer_model", lambda config: fake_reviewer()
    )
    payload = review_trace(root, report["run"]["id"], reviewer_config())
    assert payload["status"] == "completed"
    assert payload["run_id"] == report["run"]["id"]
    assert payload["trace_sha256"] == reference["sha256"]
    assert payload["observations"][0]["text"].startswith("The agent read")
    assert PrivateStorage(root).read_json(payload["id"] + ".json") == payload


def test_review_fails_closed_on_tampered_trace(tmp_path, monkeypatch):
    root = tmp_path / "private"
    report = captured_run(root, monkeypatch)
    key = report["run"]["trace"]["storage_key"]
    path = root / key
    path.chmod(0o600)
    path.write_text(
        json.dumps({"format": "workshop-benchmark-trace-1", "cases": []})
    )
    with pytest.raises(ValueError, match="hash"):
        review_trace(root, report["run"]["id"], reviewer_config())


def test_unparsable_review_is_recorded_as_failed(tmp_path, monkeypatch):
    import workshop.agent_eval.review_runner as runner

    root = tmp_path / "private"
    report = captured_run(root, monkeypatch)
    monkeypatch.setattr(
        runner,
        "resolve_llm_model",
        lambda name: ReviewBackend(),
    )
    monkeypatch.setattr(
        runner,
        "build_reviewer_model",
        lambda config: fake_reviewer(content="not json"),
    )
    payload = review_trace(root, report["run"]["id"], reviewer_config())
    assert payload["status"] == "failed"
    assert payload["diagnostic"]


def test_unreachable_server_is_infrastructure_error(tmp_path, monkeypatch):
    import workshop.agent_eval.review_runner as runner

    root = tmp_path / "private"
    report = captured_run(root, monkeypatch)

    class Unreachable:
        def format_message(self, **kwargs):
            return dict(kwargs)

        def query(self, messages):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(
        runner,
        "resolve_llm_model",
        lambda name: ReviewBackend(),
    )
    monkeypatch.setattr(
        runner, "build_reviewer_model", lambda config: Unreachable()
    )
    with pytest.raises(RuntimeError):
        review_trace(root, report["run"]["id"], reviewer_config())


def test_prompt_marks_trace_as_untrusted_data(tmp_path, monkeypatch):
    import workshop.agent_eval.review_runner as runner

    root = tmp_path / "private"
    report = captured_run(root, monkeypatch)
    seen = []
    monkeypatch.setattr(
        runner,
        "resolve_llm_model",
        lambda name: ReviewBackend(),
    )
    monkeypatch.setattr(
        runner,
        "build_reviewer_model",
        lambda config: fake_reviewer(
            content=json.dumps({"observations": []}), record=seen
        ),
    )
    review_trace(root, report["run"]["id"], reviewer_config())
    system, user = seen[0]
    assert "data" in system["content"]
    assert "instructions" in system["content"]
    assert "<trace>" in user["content"]


def test_proposals_require_real_observations(tmp_path):
    root = tmp_path / "private"
    review = record_trace_review(
        root,
        {
            "run_id": "run-a",
            "trace_storage_key": "trace-x.json",
            "trace_sha256": "a" * 64,
            "reviewer_model": "local",
            "observations": [{"text": "Observed behavior"}],
            "truncated": False,
            "truncated_chars": 0,
            "status": "completed",
        },
    )
    record_proposal(
        root,
        review["id"],
        "prompt-change",
        "Tighten the review prompt",
        [{"review_id": review["id"], "observation": 0}],
        {"suggested_change": "Ask for file paths"},
    )
    with pytest.raises(ValueError):
        record_proposal(
            root,
            review["id"],
            "prompt-change",
            "Bad evidence",
            [{"review_id": review["id"], "observation": 9}],
            {},
        )
    with pytest.raises(ValueError):
        record_proposal(
            root,
            review["id"],
            "not-a-kind",
            "Bad kind",
            [{"review_id": review["id"], "observation": 0}],
            {},
        )
    proposal_id = load_proposals(root)["proposals"][0]["id"]
    record_proposal_decision(
        root, proposal_id, "reject", "ivan", "Not useful yet"
    )
    listed = load_proposals(root)
    assert listed["proposals"][0]["latest_decision"]["decision"] == "reject"


def test_eval_cli_end_to_end(tmp_path, monkeypatch):
    import workshop.agent_eval.review_runner as runner

    root = tmp_path / "private"
    report = captured_run(root, monkeypatch)
    monkeypatch.setattr(
        runner,
        "resolve_llm_model",
        lambda name: ReviewBackend(),
    )
    monkeypatch.setattr(
        runner, "build_reviewer_model", lambda config: fake_reviewer()
    )
    config = tmp_path / "reviewer.yaml"
    config.write_text(
        "agents:\n  reviewer:\n    model:\n      model_name: local-reviewer\n"
        "      protocol: native\n"
    )
    runner_result = CliRunner().invoke(
        cli,
        [
            "eval",
            "review-trace",
            report["run"]["id"],
            "--config",
            str(config),
            "--agent",
            "reviewer",
            "--storage",
            str(root),
        ],
    )
    assert runner_result.exit_code == 0, runner_result.output
    assert "not network-isolated" in runner_result.stderr.lower()
    assert "synthetic" in runner_result.stderr.lower()
    review = json.loads(runner_result.stdout)
    listed = CliRunner().invoke(
        cli, ["eval", "inspect", review["id"], "--storage", str(root)]
    )
    assert listed.exit_code == 0, listed.output
    propose = CliRunner().invoke(
        cli,
        [
            "eval",
            "propose",
            review["id"],
            "--kind",
            "prompt-change",
            "--observation",
            "0",
            "--rationale",
            "Ask for file paths",
            "--payload",
            '{"suggested_change": "Include paths"}',
            "--storage",
            str(root),
        ],
    )
    assert propose.exit_code == 0, propose.output
    proposal = json.loads(propose.stdout)
    decide = CliRunner().invoke(
        cli,
        [
            "eval",
            "decide",
            proposal["id"],
            "--decision",
            "reject",
            "--reviewer",
            "ivan",
            "--rationale",
            "Needs evidence",
            "--storage",
            str(root),
        ],
    )
    assert decide.exit_code == 0, decide.output
    proposals = CliRunner().invoke(
        cli, ["eval", "proposals", "--storage", str(root)]
    )
    assert proposals.exit_code == 0, proposals.output
    assert (
        json.loads(proposals.stdout)["proposals"][0]["latest_decision"][
            "decision"
        ]
        == "reject"
    )


def test_proxy_environment_fails_external_requests_closed():
    env = local_only_environment()
    assert "127.0.0.1" in env["NO_PROXY"]
    assert "localhost" in env["NO_PROXY"]
    for key in ("HTTP_PROXY", "HTTPS_PROXY"):
        assert env[key].startswith("http://127.0.0.1")
