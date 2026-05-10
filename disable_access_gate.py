from pathlib import Path
import re

p = Path("backend/app/core/security.py")
s = p.read_text(encoding="utf-8")

backup = Path("backend/app/core/security.py.bak")
backup.write_text(s, encoding="utf-8")

pattern = r"async def require_access_code\(.*?\n(?=def parse_authorization_access_code)"
match = re.search(pattern, s, flags=re.S)

if not match:
raise SystemExit("Could not find require_access_code block")

replacement = '''
async def require_access_code(response: Response):
# TEMPORARY PILOT BYPASS
return {
"auth_subject": "access_code",
"auth_source": "bypass",
"has_access_header": False,
"has_access_cookie": False,
}

'''

s = s[:match.start()] + replacement + s[match.end():]
p.write_text(s, encoding="utf-8")

print("Access-code gate disabled.")
print("Backup saved:", backup)
