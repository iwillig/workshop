import json

import pytest
from pydantic import ValidationError

from workshop.agent_benchmark.contracts import Case, CaseRef, Suite
from workshop.agent_eval.contracts import (
    CaseResult,
    Outcome,
    RunResult,
    TraceReference,
    aggregate_outcomes,
)


HASH = "a" * 64


def test_case_and_suite_round_trip():
    case = Case(
        id="fix-01",
        version=1,
        role="coding",
        task="Fix the bug",
        fixture="fixture-v1",
        fixture_sha256=HASH,
        scoring_method="tests",
        scoring_version=1,
    )
    suite = Suite(
        id="coding",
        version=1,
        role="coding",
        cases=[CaseRef(id=case.id, version=case.version)],
    )
    assert Case.model_validate_json(case.model_dump_json()) == case
    assert Suite.model_validate_json(suite.model_dump_json()) == suite
    assert json.loads(case.model_dump_json())["schema_version"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "../escape"},
        {"version": 0},
        {"schema_version": 2},
        {"role": "unknown"},
        {"fixture_sha256": "bad"},
        {"task": ""},
        {"unknown": True},
    ],
)
def test_case_rejects_invalid_data(changes):
    data = dict(
        id="case",
        version=1,
        role="coding",
        task="fix",
        fixture="fixture",
        fixture_sha256=HASH,
        scoring_method="tests",
        scoring_version=1,
    )
    with pytest.raises(ValidationError):
        Case.model_validate(data | changes)


def test_suite_rejects_empty_and_duplicate_cases():
    base = dict(id="suite", version=1, role="review")
    with pytest.raises(ValidationError):
        Suite(**base, cases=[])
    with pytest.raises(ValidationError):
        Suite(**base, cases=[CaseRef(id="one", version=1)] * 2)


def test_trace_and_run_preserve_missing_usage_and_statuses():
    trace = TraceReference(
        id="trace-1",
        format="mini-swe-agent-1.1",
        sha256=HASH,
        storage_key="trace-1.json",
        source="agent",
        redacted=False,
    )
    results = [
        CaseResult(case_id=f"c-{i}", case_version=1, outcome=status)
        for i, status in enumerate(Outcome)
    ]
    run = RunResult(
        id="run-1",
        suite_id="suite",
        suite_version=1,
        suite_sha256=HASH,
        agent_id="reviewer",
        results=results,
        trace=trace,
    )
    assert RunResult.model_validate_json(run.model_dump_json()) == run
    assert run.input_tokens is None and run.cost is None
    assert aggregate_outcomes(results) == {
        status.value: 1 for status in Outcome
    }
    assert aggregate_outcomes([]) == {status.value: 0 for status in Outcome}


def test_trace_rejects_unsafe_storage_reference():
    with pytest.raises(ValidationError):
        TraceReference(
            id="trace",
            format="v1",
            sha256=HASH,
            storage_key="../secret.json",
            source="agent",
            redacted=False,
        )


def test_case_result_accepts_wire_value_but_rejects_unknown_outcome():
    data = {"case_id": "case", "case_version": 1, "outcome": "pass"}
    assert CaseResult.model_validate(data).outcome is Outcome.PASS
    with pytest.raises(ValidationError):
        CaseResult.model_validate(data | {"outcome": "success"})


def test_case_result_rejects_negative_usage():
    with pytest.raises(ValidationError):
        CaseResult(
            case_id="case", case_version=1, outcome="pass", duration_seconds=-1
        )
