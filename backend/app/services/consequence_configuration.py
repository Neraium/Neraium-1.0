"""Explicit acquisition configuration; engineering units never identify resources."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from neraium_consequence import RESOURCE_PROFILES
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConsequenceSignalConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    resource_type: str
    consequence_profile_key: str
    rate_unit: str
    max_gap_seconds: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def accept_frozen_mapping(cls, value):
        return dict(value) if isinstance(value, Mapping) else value

    @model_validator(mode="after")
    def consistent_profile(self) -> ConsequenceSignalConfiguration:
        profile = RESOURCE_PROFILES.get(self.consequence_profile_key)
        if profile is None or (self.resource_type, self.rate_unit) != (
            profile.resource_type,
            profile.rate_unit,
        ):
            raise ValueError(
                "Explicit resource and rate unit must match the consequence profile."
            )
        return self


class ConsequenceConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: dict[UUID, ConsequenceSignalConfiguration] = Field(max_length=64)


def validate_consequence_configuration(value: object) -> dict:
    return ConsequenceConfiguration.model_validate(value).model_dump(mode="json")
