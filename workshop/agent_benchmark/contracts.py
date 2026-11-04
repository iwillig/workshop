"""Versioned benchmark definitions; no runner or execution side effects."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Version = Annotated[int, Field(strict=True, ge=1)]
NonEmpty = Annotated[str, Field(min_length=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal[1] = 1


class CaseRef(Contract):
    id: Identifier
    version: Version


class Case(Contract):
    id: Identifier
    version: Version
    role: Literal["coding", "review", "pr-review"]
    task: NonEmpty
    fixture: Identifier
    fixture_sha256: Digest
    scoring_method: Identifier
    scoring_version: Version
    constraints: tuple[str, ...] = ()


class Suite(Contract):
    id: Identifier
    version: Version
    role: Literal["coding", "review", "pr-review"]
    cases: list[CaseRef] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_cases(self):
        keys = [(case.id, case.version) for case in self.cases]
        if len(keys) != len(set(keys)):
            raise ValueError("suite case references must be unique")
        return self
