# Frozen target baseline
Target: /home/ubuntu/Neraium-1.0. HEAD a4ea0a992841d281e19de8119ecd1275a0d7e654, branch fix/deterministic-governed-output. Common ancestor: 97d267d317fcce4b4424cf2141e97e87680acfc0.

Before any repository writes, every entry in both frozen manifests from /tmp/neraium-integration-freeze-653p6dk1 was hashed against the current file: zero missing or changed entries. The original SOURCE_HASHES.json and TARGET_PREINTEGRATION_HASHES.json are copied byte-for-byte, not regenerated. Scope is tracked and non-ignored untracked files; ignored dependency/cache/runtime files are excluded, as in the originals.

The target descendant commit adds validation evidence and reporting scripts, not production changes. Its current dirty worktree adds further determinism/source identity behavior, tests and retained validation artifacts. None was overwritten. No benchmark runtime state, generated telemetry, database, virtual environment, cache or giant raw evidence was copied into target.

The final manifest reports unchanged original target files and the new reporting files. Because promotion stopped before implementation, POSTINTEGRATION is the requested filename for a post-audit manifest, not a claim of completed integration. Manifests exclude their own post-audit digest to avoid self-reference.
