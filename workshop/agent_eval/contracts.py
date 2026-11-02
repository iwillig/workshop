"""Versioned evaluation records and outcome counting."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Version = Annotated[int, Field(strict=True, ge=1)]
StorageKey = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.json$")
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal[1] = 1


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PENDING_HUMAN_REVIEW = "pending_human_review"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


class TraceReference(Contract):
    id: Identifier
    format: Annotated[str, Field(min_length=1)]
    sha256: Digest
    storage_key: StorageKey
    source: Annotated[str, Field(min_length=1)]
    redacted: bool


class CaseResult(Contract):
    case_id: Identifier
    case_version: Version
    outcome: Outcome = Field(strict=False)
    duration_seconds: (
        Annotated[float, Field(ge=0, allow_inf_nan=False)] | None
    ) = None
    diagnostic: str | None = None


class RunResult(Contract):
    id: Identifier
    suite_id: Identifier
    suite_version: Version
    suite_sha256: Digest
    agent_id: Identifier
    results: list[CaseResult]
    trace: TraceReference | None = None
    input_tokens: Annotated[int, Field(strict=True, ge=0)] | None = None
    output_tokens: Annotated[int, Field(strict=True, ge=0)] | None = None
    cost: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None


def aggregate_outcomes(results: list[CaseResult]) -> dict[str, int]:
    """Count each outcome separately; never infer an overall pass."""
    counts = {outcome.value: 0 for outcome in Outcome}
    for result in results:
        counts[result.outcome.value] += 1
    return counts
