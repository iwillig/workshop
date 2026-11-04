"""Opt-in live probe: local review succeeds, external requests fail closed.

Requires a running llama-server with a registered local reviewer model.
May download model data on first use if the server is not already warm.
"""

import os

import httpx
import pytest

from workshop.agent_benchmark.local import run_suite
from workshop.agent_config import load_config
from workshop.agent_eval.review_runner import (
    apply_local_only_environment,
    local_only_environment,
    review_trace,
    validate_reviewer_config,
)


def _required_env(name):
    value = os.environ.get(name)
    if not value:
        pytest.fail(f"Set {name} for the trace-review probe")
    return value


@pytest.mark.skipif(
    os.environ.get("WORKSHOP_TRACE_REVIEW_PROBE") != "1",
    reason="set WORKSHOP_TRACE_REVIEW_PROBE=1 with a local llama-server",
)
def test_local_review_succeeds_and_external_fails_closed(tmp_path):
    config_path = _required_env("WORKSHOP_TRACE_REVIEW_CONFIG")
    agent_name = _required_env("WORKSHOP_TRACE_REVIEW_AGENT")

    class SavingAgent:
        progress_sink = None

        def run(self, inner_task):
            self.task = inner_task
            return {"exit_status": "Submitted", "submission": "done"}

        def save(self, path, *extra):
            return {"messages": [{"role": "user", "content": self.task}]}

    import workshop.agent_config as agent_config_module

    original_build = agent_config_module.build_agent
    agent_config_module.build_agent = lambda config: SavingAgent()
    try:
        report = run_suite(
            "review-v1",
            {},
            "reviewer",
            tmp_path / "records",
            local=True,
            capture_trace=True,
        )
    finally:
        agent_config_module.build_agent = original_build

    reviewer = load_config(config_path, agent_name=agent_name)
    validate_reviewer_config(reviewer)
    with apply_local_only_environment():
        with pytest.raises(httpx.HTTPError):
            httpx.get("http://203.0.113.1/", timeout=5)
        payload = review_trace(
            tmp_path / "records", report["run"]["id"], reviewer
        )
    assert payload["status"] == "completed", payload["diagnostic"]
    assert local_only_environment()["NO_PROXY"]
