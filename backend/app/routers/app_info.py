from fastapi import APIRouter

router = APIRouter(tags=["app"])


@router.get("/app")
def read_app_metadata() -> dict[str, str]:
    return {
        "name": "Neraium",
        "subtitle": "Operational relationship intelligence for hospitality aquatic infrastructure",
        "description": (
            "Neraium helps resort pool and spa operations teams detect and explain "
            "persistent relationship instability across telemetry domains."
        ),
        "environment": "development",
        "version": "0.1.0",
    }
