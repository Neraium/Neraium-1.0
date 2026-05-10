from fastapi import Request, Response


def require_api_access(request: Request, response: Response) -> None:
    request.state.auth_context = {
        "auth_subject": "public",
        "auth_source": "bypass",
        "has_access_header": False,
        "has_access_cookie": False,
    }
