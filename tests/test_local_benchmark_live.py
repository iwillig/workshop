"""Explicit opt-in live smoke test; may send fixture data to a provider."""

import os

import pytest

from workshop.agent_benchmark.local import run_suite
from workshop.agent_config import load_config
from workshop.agent_eval.storage import PrivateStorage


@pytest.mark.skipif(
    os.environ.get("WORKSHOP_BENCHMARK_LIVE") != "1",
    reason="set WORKSHOP_BENCHMARK_LIVE=1 to run a real local agent",
)
def test_live_review_benchmark(tmp_path):
    config_path = os.environ["WORKSHOP_BENCHMARK_AGENT_CONFIG"]
    agent_name = os.environ["WORKSHOP_BENCHMARK_AGENT_NAME"]
    report = run_suite(
        "review-v1",
        load_config(config_path, agent_name=agent_name),
        agent_name,
        tmp_path / "records",
        local=True,
    )
    result = report["run"]["results"][0]
    assert result["outcome"] == "pending_human_review", result["diagnostic"]


@pytest.mark.skipif(
    os.environ.get("WORKSHOP_BENCHMARK_CODING_LIVE") != "1",
    reason="set WORKSHOP_BENCHMARK_CODING_LIVE=1 to run a real coding agent",
)
def test_live_coding_benchmark(tmp_path):
    config_path = os.environ["WORKSHOP_BENCHMARK_CODING_CONFIG"]
    agent_name = os.environ["WORKSHOP_BENCHMARK_CODING_AGENT"]
    storage = tmp_path / "records"
    report = run_suite(
        "coding-v1",
        load_config(config_path, agent_name=agent_name),
        agent_name,
        storage,
        local=True,
    )
    result = report["run"]["results"][0]
    assert result["outcome"] in {"pass", "fail"}, result["diagnostic"]
    assert (
        PrivateStorage(storage).read_json(report["run"]["id"] + ".json")
        == report
    )
