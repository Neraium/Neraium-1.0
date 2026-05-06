from fastapi import APIRouter

router = APIRouter(tags=["app"])


@router.get("/app")
def read_app_metadata() -> dict[str, str]:
    return {
        "name": "Neraium",
        "subtitle": "Environmental drift intelligence for cannabis grow facilities",
        "description": (
            "Neraium helps cannabis cultivation teams detect and explain "
            "environmental drift before it becomes crop stress."
        ),
        "environment": "development",
        "version": "0.1.0",
    }
