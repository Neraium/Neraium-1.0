from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.consequence_quantification import RESOURCE_PROFILES, quantify_consequence


router = APIRouter(prefix="/consequence", tags=["consequence"])


class ConsequenceObservation(BaseModel):
    timestamp: str | float
    observed: float
    expected: float
    valid: bool = True


class ConsequenceQuantificationRequest(BaseModel):
    profile_key: str
    observations: list[ConsequenceObservation] = Field(min_length=2)
    max_gap_seconds: float | None = Field(default=None, gt=0)
    source_relationship_ids: list[str] = Field(default_factory=list)
    source_tag_ids: list[str] = Field(default_factory=list)
    support_level: str | None = None


@router.get("/profiles")
def list_profiles() -> dict[str, Any]:
    return {
        "profiles": {
            key: {
                "resource_type": value.resource_type,
                "rate_unit": value.rate_unit,
                "cumulative_unit": value.cumulative_unit,
                "rate_period_seconds": value.rate_period_seconds,
            }
            for key, value in RESOURCE_PROFILES.items()
        }
    }


@router.post("/quantify")
def quantify(request: ConsequenceQuantificationRequest) -> dict[str, Any]:
    return quantify_consequence(
        (item.model_dump() for item in request.observations),
        profile_key=request.profile_key,
        max_gap_seconds=request.max_gap_seconds,
        source_relationship_ids=request.source_relationship_ids,
        source_tag_ids=request.source_tag_ids,
        support_level=request.support_level,
    )
