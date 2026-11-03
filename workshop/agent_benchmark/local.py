"""Report-only benchmarks for trusted local development, not isolation."""

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from workshop.agent_benchmark.contracts import Case, CaseRef, Suite
from workshop.agent_eval.contracts import (
    CaseResult,
    Outcome,
    RunResult,
    aggregate_outcomes,
)
from workshop.agent_eval.storage import PrivateStorage

_ROOT = Path(__file__).parent
_DEFINITIONS = {
    "coding-v1": {
        "role": "coding",
        "id": "sum-values",
        "task": "Implement total(values) in calculator.py to return the sum.",
        "fixture_hash": (
            "bd6c6dc5b4a00327889802f4b7e5a1575f3fd85a3c7ae9affe30f17d882f8b2a"
        ),
        "check_hash": (
            "b8e76773036b048f9dcd76cf221a7011adc8e91c988a46d0837639bb5fac7c5c"
        ),
    },
    "review-v1": {
        "role": "review",
        "id": "average-empty",
        "task": (
            "Review calculator.py for bugs. Report findings with locations."
        ),
        "fixture_hash": (
            "9621c2c601b7c0d9e6b57764794f975c13d189eb4cf11fb820a1f6791d645250"
        ),
        "check_hash": (
            "ae4ae22c87b289556e1384b821be9d1dc854de6291d8c40c8c5778951a2b692a"
        ),
    },
}


@dataclass(frozen=True)
class LocalCase:
    case: Case
    fixture: Path
    check: Path
    files: tuple[str, ...] = ("calculator.py",)


@dataclass(frozen=True)
class LocalSuite:
    suite: Suite
    cases: tuple[LocalCase, ...]
    sha256: str


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_suite(name):
    """Load and verify one of the fixed, versioned development suites."""
    if name in {"coding-v2", "review-v2"}:
        return _load_v2(name)
    if name not in _DEFINITIONS:
        raise ValueError(f"Unknown suite: {name}")
    definition = _DEFINITIONS[name]
    role = definition["role"]
    fixture = _ROOT / "fixtures" / role
    check = (
        _ROOT / "checks" / ("coding.py" if role == "coding" else "review.txt")
    )
    if _digest(fixture / "calculator.py") != definition["fixture_hash"]:
        raise ValueError(f"Fixture hash mismatch for {name}")
    if _digest(check) != definition["check_hash"]:
        raise ValueError(f"Scoring hash mismatch for {name}")
    case = Case(
        id=definition["id"],
        version=1,
        role=role,
        task=definition["task"],
        fixture=role,
        fixture_sha256=definition["fixture_hash"],
        scoring_method="python-check" if role == "coding" else "human-review",
        scoring_version=1,
    )
    suite = Suite(
        id=name,
        version=1,
        role=role,
        cases=[CaseRef(id=case.id, version=case.version)],
    )
    fingerprint = json.dumps(
        {
            "suite": suite.model_dump(),
            "case": case.model_dump(),
            "check_sha256": definition["check_hash"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return LocalSuite(
        suite,
        (LocalCase(case, fixture, check),),
        hashlib.sha256(fingerprint).hexdigest(),
    )


def _load_v2(name):
    role = name.removesuffix("-v2")
    original = load_suite(role + "-v1")
    definitions = json.loads((_ROOT / "fixtures" / "v2.json").read_text())
    cases = list(original.cases)
    fingerprints = [
        {
            "case": cases[0].case.model_dump(),
            "check_sha256": _digest(cases[0].check),
        }
    ]
    for definition in definitions:
        if definition["role"] != role:
            continue
        fixture_name = definition["fixture"]
        if Path(fixture_name).name != fixture_name:
            raise ValueError("Invalid fixture name")
        fixture = _ROOT / "fixtures" / fixture_name
        files = definition["files"]
        for relative, digest in files.items():
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError("Invalid fixture path")
            if _digest(fixture / path) != digest:
                raise ValueError(f"Fixture hash mismatch for {relative}")
        check_name = definition["check"]
        if Path(check_name).name != check_name:
            raise ValueError("Invalid scoring path")
        check = _ROOT / "checks" / check_name
        if _digest(check) != definition["check_sha256"]:
            raise ValueError(f"Scoring hash mismatch for {check_name}")
        fixture_hash = hashlib.sha256(
            json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        case = Case(
            id=definition["id"],
            version=1,
            role=role,
            task=definition["task"],
            fixture=fixture_name,
            fixture_sha256=fixture_hash,
            scoring_method="python-check"
            if role == "coding"
            else "human-review",
            scoring_version=1,
        )
        cases.append(LocalCase(case, fixture, check, tuple(files)))
        fingerprints.append(
            {
                "case": case.model_dump(),
                "files": files,
                "check_sha256": definition["check_sha256"],
            }
        )
    if len(cases) != 3:
        raise ValueError(f"Invalid case count for {name}")
    suite = Suite(
        id=name,
        version=2,
        role=role,
        cases=[
            CaseRef(id=item.case.id, version=item.case.version)
            for item in cases
        ],
    )
    fingerprint = json.dumps(
        {"suite": suite.model_dump(), "cases": fingerprints},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return LocalSuite(
        suite, tuple(cases), hashlib.sha256(fingerprint).hexdigest()
    )


def execute_agent(task, workspace, config):
    """Run an existing agent locally; limits are cooperative, not isolation."""
    from workshop.agent_config import build_agent

    config = copy.deepcopy(config)
    environment = config.setdefault("environment", {})
    if environment.get("environment_class", "local") != "local":
        raise ValueError("Local benchmarks require a local environment")
    environment["cwd"] = str(workspace)
    if not environment.get("timeout"):
        environment["timeout"] = 30
    options = config.setdefault("agent", {})
    if not options.get("step_limit"):
        options["step_limit"] = 20
    if not options.get("wall_time_limit_seconds"):
        options["wall_time_limit_seconds"] = 120
    # Do not let an agent configuration write a trajectory outside storage.
    options.pop("output_path", None)
    agent = build_agent(config)
    if hasattr(agent, "progress_sink"):
        import click

        agent.progress_sink = lambda text: click.echo(text, err=True)
    return agent.run(task)


def run_suite(
    name, config, agent_id, storage_root, *, local=False, execute=None
):
    """Run trusted fixtures on the host and save a private report."""
    if local is not True:
        raise ValueError(
            "Explicit local execution acknowledgement is required"
        )
    CaseRef(id=agent_id, version=1)
    suite = load_suite(name)
    storage = PrivateStorage(storage_root)
    executor = execute or execute_agent
    results, details = [], []
    for entry in suite.cases:
        started = time.monotonic()
        diagnostic = None
        findings = None
        outcome = Outcome.INFRASTRUCTURE_ERROR
        try:
            with tempfile.TemporaryDirectory(
                prefix="workshop-benchmark-"
            ) as tmp:
                workspace = Path(tmp) / "workspace"
                workspace.mkdir()
                for relative in entry.files:
                    destination = workspace / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(entry.fixture / relative, destination)
                agent_result = executor(entry.case.task, workspace, config)
                if agent_result.get("cleanup_warning"):
                    diagnostic = str(agent_result["cleanup_warning"])
                elif agent_result.get("exit_status") != "Submitted":
                    diagnostic = "Agent did not submit: " + str(
                        agent_result.get("exit_status", "unknown")
                    )
                elif entry.case.role == "review":
                    findings = str(agent_result.get("submission") or "")
                    outcome = Outcome.PENDING_HUMAN_REVIEW
                else:
                    completed = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            str(entry.check),
                            str(workspace),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=30,
                        check=False,
                    )
                    if completed.returncode < 0:
                        outcome = Outcome.INFRASTRUCTURE_ERROR
                    elif completed.returncode == 0:
                        outcome = Outcome.PASS
                    else:
                        outcome = Outcome.FAIL
                    if completed.returncode:
                        diagnostic = (
                            f"Coding check exited {completed.returncode}"
                        )
        except Exception as exc:
            outcome = Outcome.INFRASTRUCTURE_ERROR
            diagnostic = f"{type(exc).__name__}: {exc}"
        results.append(
            CaseResult(
                case_id=entry.case.id,
                case_version=entry.case.version,
                outcome=outcome,
                duration_seconds=time.monotonic() - started,
                diagnostic=diagnostic,
            )
        )
        details.append(
            {
                "case_id": entry.case.id,
                "findings": findings,
                "expected_findings": entry.check.read_text()
                if entry.case.role == "review"
                else None,
            }
        )
    run = RunResult(
        id="run-" + uuid.uuid4().hex,
        suite_id=suite.suite.id,
        suite_version=suite.suite.version,
        suite_sha256=suite.sha256,
        agent_id=agent_id,
        results=results,
    )
    report = {
        "run": run.model_dump(mode="json"),
        "counts": aggregate_outcomes(results),
        "model": (config.get("model") or {}).get("model_name"),
        "details": details,
    }
    storage.write_json(run.id + ".json", report)
    return report
