"""Private trace reviews, improvement proposals, and human decisions."""

import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from workshop.agent_eval.storage import PrivateStorage
from workshop.agent_eval.contracts import (
    Contract,
    Digest,
    Identifier,
    StorageKey,
    Version,
)

PROMPT_VERSION = 1
_TEXT = Annotated[str, Field(min_length=1, max_length=2000)]


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    text: _TEXT
    evidence: Annotated[str, Field(max_length=2000)] | None = None


class TraceReview(Contract):
    id: Identifier
    run_id: Identifier
    trace_storage_key: StorageKey
    trace_sha256: Digest
    reviewer_model: _TEXT
    prompt_version: Version
    observations: Annotated[list[Observation], Field(max_length=20)]
    truncated: bool
    truncated_chars: Annotated[int, Field(strict=True, ge=0)]
    created_at: str
    status: Literal["completed", "failed"]
    diagnostic: Annotated[str, Field(max_length=2000)] | None = None


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    review_id: Identifier
    observation: Annotated[int, Field(strict=True, ge=0)]


class Proposal(Contract):
    id: Identifier
    review_id: Identifier
    kind: Literal["eval-case", "prompt-change", "skill-note"]
    rationale: _TEXT
    evidence: Annotated[list[Evidence], Field(min_length=1, max_length=20)]
    payload: Annotated[
        dict[str, Annotated[str, Field(max_length=2000)]],
        Field(max_length=20),
    ]
    status: Literal["proposed"] = "proposed"
    created_at: str


class ProposalDecision(Contract):
    id: Identifier
    proposal_id: Identifier
    decision: Literal["accept", "reject", "revise"]
    reviewer: _TEXT
    rationale: _TEXT
    recorded_at: str


def _now():
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _validate_review(storage_root, review_id):
    data = PrivateStorage(storage_root).read_json(review_id + ".json")
    review = TraceReview.model_validate(data)
    if review.id != review_id:
        raise ValueError("Review ID does not match record")
    return review


def record_trace_review(storage_root, data):
    """Store one reviewer record with a generated identity and timestamp."""
    review = TraceReview(
        id="trace-review-" + uuid.uuid4().hex,
        prompt_version=PROMPT_VERSION,
        created_at=_now(),
        **data,
    )
    payload = review.model_dump(mode="json")
    PrivateStorage(storage_root).write_json(review.id + ".json", payload)
    return payload


def load_trace_review(storage_root, review_id):
    return _validate_review(storage_root, review_id).model_dump(mode="json")


def record_proposal(
    storage_root, review_id, kind, rationale, evidence, payload
):
    """Store a descriptive proposal linked to verified observations."""
    review = _validate_review(storage_root, review_id)
    evidence = [
        dict(item, review_id=review_id) if isinstance(item, dict) else item
        for item in evidence
    ]
    proposal = Proposal(
        id="proposal-" + uuid.uuid4().hex,
        review_id=review_id,
        kind=kind,
        rationale=rationale,
        evidence=evidence,
        payload=payload,
        created_at=_now(),
    )
    for item in proposal.evidence:
        if item.observation >= len(review.observations):
            raise ValueError(
                "Evidence must reference an existing observation index"
            )
    stored = proposal.model_dump(mode="json")
    PrivateStorage(storage_root).write_json(proposal.id + ".json", stored)
    return stored


def record_proposal_decision(
    storage_root, proposal_id, decision, reviewer, rationale
):
    """Append an attributable decision without changing the proposal."""
    storage = PrivateStorage(storage_root)
    storage.read_json(proposal_id + ".json")
    entry = ProposalDecision(
        id="proposal-decision-" + uuid.uuid4().hex,
        proposal_id=proposal_id,
        decision=decision,
        reviewer=reviewer,
        rationale=rationale,
        recorded_at=_now(),
    )
    payload = entry.model_dump(mode="json")
    storage.write_json(entry.id + ".json", payload)
    return payload


def load_proposals(storage_root):
    """List proposals with their full decision history and latest state."""
    storage = PrivateStorage(storage_root)
    decisions = []
    for name in os.listdir(storage.root):
        if name.startswith("proposal-decision-"):
            decisions.append(
                ProposalDecision.model_validate(storage.read_json(name))
            )
    decisions.sort(key=lambda item: (item.recorded_at, item.id))
    proposals = []
    for name in os.listdir(storage.root):
        if not name.startswith("proposal-") or name.startswith(
            "proposal-decision-"
        ):
            continue
        proposal = Proposal.model_validate(storage.read_json(name))
        history = [
            item.model_dump(mode="json")
            for item in decisions
            if item.proposal_id == proposal.id
        ]
        proposals.append(
            proposal.model_dump(mode="json")
            | {
                "decisions": history,
                "latest_decision": history[-1] if history else None,
            }
        )
    return {"proposals": proposals}
