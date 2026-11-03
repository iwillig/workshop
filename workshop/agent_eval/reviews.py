"""Private, attributable human judgments for local benchmark reports."""

import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from workshop.agent_eval.contracts import (
    Digest,
    Identifier,
    Outcome,
    RunResult,
)
from workshop.agent_eval.storage import PrivateStorage


class ReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    id: Identifier
    run_id: Identifier
    case_id: Identifier
    case_version: Annotated[int, Field(strict=True, ge=1)]
    suite_sha256: Digest
    decision: Literal["pass", "fail", "inconclusive"]
    reviewer: Annotated[str, Field(min_length=1)]
    rationale: Annotated[str, Field(min_length=1)]
    recorded_at: str


def _read_run(storage, run_id):
    report = storage.read_json(run_id + ".json")
    run = RunResult.model_validate(report["run"])
    if run.id != run_id:
        raise ValueError("Run ID does not match record")
    return report, run


def record_review(
    storage_root, run_id, case_id, decision, reviewer, rationale
):
    """Append a separate human judgment without changing the original run."""
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("Reviewer is required")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("Rationale is required")
    storage = PrivateStorage(storage_root)
    _, run = _read_run(storage, run_id)
    cases = [case for case in run.results if case.case_id == case_id]
    if len(cases) != 1 or cases[0].outcome != Outcome.PENDING_HUMAN_REVIEW:
        raise ValueError("Case must have exactly one pending review result")
    review = ReviewRecord(
        id="review-" + uuid.uuid4().hex,
        run_id=run.id,
        case_id=case_id,
        case_version=cases[0].case_version,
        suite_sha256=run.suite_sha256,
        decision=decision,
        reviewer=reviewer.strip(),
        rationale=rationale.strip(),
        recorded_at=datetime.now(UTC).isoformat(timespec="microseconds"),
    )
    payload = review.model_dump(mode="json")
    storage.write_json(review.id + ".json", payload)
    return payload


def load_report(storage_root, run_id):
    """Read the original report and attach human judgments and counts."""
    storage = PrivateStorage(storage_root)
    report, run = _read_run(storage, run_id)
    pending = {
        (case.case_id, case.case_version)
        for case in run.results
        if case.outcome == Outcome.PENDING_HUMAN_REVIEW
    }
    reviews = []
    for name in os.listdir(storage.root):
        if not name.startswith("review-") or not name.endswith(".json"):
            continue
        review = ReviewRecord.model_validate(storage.read_json(name))
        if (
            review.run_id == run.id
            and review.suite_sha256 == run.suite_sha256
            and (review.case_id, review.case_version) in pending
        ):
            reviews.append(review)
    reviews.sort(key=lambda item: (item.recorded_at, item.id))
    latest = {(item.case_id, item.case_version): item for item in reviews}
    counts = {"pass": 0, "fail": 0, "inconclusive": 0, "pending": 0}
    for key in pending:
        counts[latest[key].decision if key in latest else "pending"] += 1
    return report | {
        "reviews": [review.model_dump(mode="json") for review in reviews],
        "review_counts": counts,
    }
