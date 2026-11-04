"""Private, hash-linked trajectory collections for benchmark runs."""

import hashlib
import json
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from workshop.agent_eval.contracts import TraceReference
from workshop.agent_eval.reviews import _read_run
from workshop.agent_eval.storage import PrivateStorage

TRACE_FORMAT = "workshop-benchmark-trace-1"


class TraceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    format: str
    cases: list[dict]


def _canonical(record):
    return json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def write_trace(storage, cases):
    """Store one trajectory per case and return its reference."""
    if not cases:
        raise ValueError("A trace requires at least one captured case")
    record = TraceRecord(format=TRACE_FORMAT, cases=list(cases))
    payload = record.model_dump(mode="json")
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    key = "trace-" + uuid.uuid4().hex + ".json"
    storage.write_json(key, payload)
    return TraceReference(
        id=key.removesuffix(".json"),
        format=TRACE_FORMAT,
        sha256=digest,
        storage_key=key,
        source="workshop-benchmark-local-runner",
        redacted=False,
    )


def load_trace(storage_root, run_id):
    """Load the trajectory collection referenced by a stored run."""
    storage = PrivateStorage(storage_root)
    _, run = _read_run(storage, run_id)
    if run.trace is None:
        raise ValueError("Run has no stored trace")
    record = storage.read_json(run.trace.storage_key)
    if hashlib.sha256(_canonical(record)).hexdigest() != run.trace.sha256:
        raise ValueError(
            "Trace record does not match the hash in its run report"
        )
    if (
        record.get("format") != TRACE_FORMAT
        or run.trace.format != TRACE_FORMAT
    ):
        raise ValueError("Trace record has an unexpected format")
    TraceRecord.model_validate(record)
    return record
