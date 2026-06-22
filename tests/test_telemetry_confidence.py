from app.services.telemetry_confidence import apply_telemetry_confidence_adjustment


def test_telemetry_confidence_adjustment_caps_score_and_room_confidence():
    intelligence = {
        "neraium_score": 88,
        "confidence_basis": "Relationship change persisted across the window.",
        "confidence_components": {"data_sufficiency": "high", "signal_strength": "high"},
        "reliability_rating": "strong",
        "rooms": [
            {
                "room": "Filtration",
                "confidence": 86,
                "confidence_basis": "Strong relationship support.",
                "confidence_components": {"data_sufficiency": "high"},
            }
        ],
        "core_sii_outputs": {
            "review_window_inference": {
                "confidence_basis": "Persistent behavior shift."
            }
        },
    }
    data_quality = {
        "normalization_report": {
            "window_suppressed": True,
        }
    }

    adjusted = apply_telemetry_confidence_adjustment(intelligence, data_quality=data_quality)

    assert adjusted["telemetry_confidence_adjusted"] is True
    assert adjusted["neraium_score"] == 55
    assert adjusted["reliability_rating"] == "weak"
    assert adjusted["confidence_components"]["data_sufficiency"] == "low"
    assert adjusted["confidence_components"]["telemetry_integrity"] == "reduced_confidence"
    assert adjusted["rooms"][0]["confidence"] == 55
    assert adjusted["rooms"][0]["telemetry_confidence_adjusted"] is True
    assert "Telemetry integrity reduced confidence" in adjusted["confidence_basis"]
    assert "Telemetry integrity reduced confidence" in adjusted["core_sii_outputs"]["review_window_inference"]["confidence_basis"]


def test_telemetry_confidence_adjustment_noops_when_window_is_not_suppressed():
    intelligence = {"neraium_score": 88, "rooms": []}
    data_quality = {"normalization_report": {"window_suppressed": False}}

    assert apply_telemetry_confidence_adjustment(intelligence, data_quality=data_quality) is intelligence
