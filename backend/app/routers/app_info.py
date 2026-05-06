from fastapi import APIRouter

router = APIRouter(tags=["app"])


@router.get("/app")
def read_app_metadata() -> dict[str, str]:
    return {
        "name": "Neraium",
        "subtitle": "Infrastructure Intelligence for Physical Systems",
        "environment": "development",
        "version": "0.1.0",
    }
