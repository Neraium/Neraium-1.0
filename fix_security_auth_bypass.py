from pathlib import Path

p = Path("backend/app/core/security.py")

if p.exists():
backup = Path("backend/app/core/security.py.bak_auth_bypass")
backup.write_text(p.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")

p.write_text("""from fastapi import Response

ACCESS_CODE_HEADER = "X-Neraium-Access-Code"
ACCESS_CODE_COOKIE = "neraium_access_code"

async def require_access_code(response: Response):
# TEMPORARY PILOT BYPASS
return {
"auth_subject": "access_code",
"auth_source": "bypass",
"has_access_header": False,
"has_access_cookie": False,
}

def parse_authorization_access_code(*args, **kwargs):
return None

def refresh_access_cookie(*args, **kwargs):
return None
""", encoding="utf-8")

print("security.py replaced with temporary auth bypass.")
