Codex rules for this repo:
- Never use apply_patch or patch helpers.
- Never check for apply_patch.
- Use direct file edits with python3, sed, perl, or cat.
- If a file edit is needed, rewrite the file directly.
- If a tool fails once, do not retry it.
- Finish with git diff, build/test, commit, and git push.
