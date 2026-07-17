# API contract policy

All 106 documented HTTP operations are inventoried by `tests/test_api_contracts.py`. Request models reject undeclared top-level fields and trim declared strings. Dynamic connector configuration remains an explicitly open nested object because each connector owns its configuration schema; its serialized size and key count are bounded.

Non-upload request bodies are capped at 1 MiB. Historical telemetry uploads use the configured `max_upload_size_bytes` limit, and connector CSV uploads use the 16 MiB connector limit. Relevant identity headers, filenames, paths, strings, URLs, enums, timestamps, pagination, and numeric controls have explicit bounds. Unknown query parameters are rejected. Replay times require timezone-aware ISO 8601 values.

Errors share `detail`, `message`, and `error_type`; validation errors also include sanitized locations and types without echoing submitted values. Upload endpoints retain their richer historical state envelope (`job_id`, processing state, progress, and error fields) for frontend compatibility, but now include the common fields when raised through shared handlers. Internal exception messages are logged and replaced with a generic client message.

The shorthand `/latest-upload` and `/systems` routes are deprecated in OpenAPI and remain compatibility aliases. Admin surfaces are the connector configuration routes, auth user/session management, audit, observability, startup status, route debug, data-connection administration, and global resets; production runtime authorization tests cover unauthenticated and insufficient-role access.
