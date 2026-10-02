"""Apply only connector-executor wiring to the production base image."""

from pathlib import Path
import os


ROOT = Path(os.environ.get("NERAIUM_CONNECTOR_OVERLAY_ROOT", "/app/app"))


def replace(path: str, before: str, after: str, *, count: int = 1) -> None:
    target = ROOT / path
    source = target.read_text()
    found = source.count(before)
    if found != count:
        raise SystemExit(f"connector overlay anchor mismatch: {path} ({found}/{count})")
    target.write_text(source.replace(before, after, count))


replace(
    "connectors/base.py",
    "    secret_binding: SecretBinding | None = None\n\n    def __post_init__(self) -> None:",
    "    secret_binding: SecretBinding | None = None\n"
    "    tenant_scope_id: str | None = None\n"
    "    workspace_id: str | None = None\n"
    "    facility_id: str | None = None\n\n"
    "    def __post_init__(self) -> None:",
)
replace(
    "connectors/base.py",
    '        if not str(self.resource_scope_id or "").strip():\n'
    '            raise ValueError("resource_scope_id_required")\n'
    "        if self.secret_binding is not None:",
    '        if not str(self.resource_scope_id or "").strip():\n'
    '            raise ValueError("resource_scope_id_required")\n'
    "        authority = (self.tenant_scope_id, self.workspace_id, self.facility_id)\n"
    "        if any(value is not None for value in authority) and not all(\n"
    "            isinstance(value, str) and value.strip() for value in authority\n"
    "        ):\n"
    '            raise ValueError("connector_scope_authority_invalid")\n'
    "        if self.secret_binding is not None:",
)
replace(
    "services/telemetry_connection_service.py",
    "            secret_binding=self._binding(scope, connection),\n        )",
    "            secret_binding=self._binding(scope, connection),\n"
    "            tenant_scope_id=scope.tenant_scope_id,\n"
    "            workspace_id=scope.workspace_id,\n"
    "            facility_id=scope.facility_id,\n        )",
)
replace(
    "services/telemetry_scheduler.py",
    "            secret_binding=secret_binding,\n        )",
    "            secret_binding=secret_binding,\n"
    "            tenant_scope_id=scope.tenant_scope_id,\n"
    "            workspace_id=scope.workspace_id,\n"
    "            facility_id=scope.facility_id,\n        )",
)
replace(
    "core/config.py",
    "    telemetry_controlled_egress_enabled: bool = False\n",
    "    telemetry_controlled_egress_enabled: bool = False\n"
    "    telemetry_executor_url: str = \"\"\n"
    "    telemetry_executor_ca_pem: str = field(default=\"\", repr=False)\n"
    "    telemetry_executor_auth_secret_arn: str = \"\"\n",
)
replace(
    "core/config.py",
    "        telemetry_controlled_egress_enabled=parse_bool(\n"
    '            os.getenv("NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED"),\n'
    "            False,\n"
    '            name="NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED",\n'
    "        ),\n",
    "        telemetry_controlled_egress_enabled=parse_bool(\n"
    '            os.getenv("NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED"),\n'
    "            False,\n"
    '            name="NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED",\n'
    "        ),\n"
    '        telemetry_executor_url=str(os.getenv("NERAIUM_TELEMETRY_EXECUTOR_URL", "")).strip(),\n'
    '        telemetry_executor_ca_pem=os.getenv("NERAIUM_TELEMETRY_EXECUTOR_CA_PEM", ""),\n'
    "        telemetry_executor_auth_secret_arn=str(\n"
    '            os.getenv("NERAIUM_TELEMETRY_EXECUTOR_AUTH_SECRET_ARN", "")\n'
    "        ).strip(),\n",
)
replace(
    "core/config.py",
    "    if settings.notification_webhook_url:\n",
    "    if settings.telemetry_executor_url:\n"
    "        endpoint = urlsplit(settings.telemetry_executor_url)\n"
    '        if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password:\n'
    '            raise ValueError("NERAIUM_TELEMETRY_EXECUTOR_URL must be an absolute HTTPS URL.")\n'
    '        if "BEGIN CERTIFICATE" not in settings.telemetry_executor_ca_pem:\n'
    '            raise ValueError("NERAIUM_TELEMETRY_EXECUTOR_CA_PEM must contain a trusted certificate.")\n'
    '        if not settings.telemetry_executor_auth_secret_arn:\n'
    '            raise ValueError("NERAIUM_TELEMETRY_EXECUTOR_AUTH_SECRET_ARN is required.")\n'
    "    if (app_env in {\"prod\", \"production\"} and settings.telemetry_database_url\n"
    "            and not (settings.telemetry_executor_url and settings.telemetry_executor_ca_pem\n"
    "                     and settings.telemetry_executor_auth_secret_arn)):\n"
    '        raise ValueError("Production telemetry requires the isolated connector executor.")\n\n'
    "    if settings.notification_webhook_url:\n",
)
replace(
    "services/telemetry_runtime.py",
    "from app.services.telemetry_domain import ConnectorType\n",
    "from app.services.telemetry_domain import ConnectorType\n"
    "from app.services.connector_execution import RemoteHttpsTelemetryConnector\n",
)
replace(
    "services/telemetry_runtime.py",
    "        providers = TelemetryProviderRegistry(\n",
    "        https_provider: TelemetryConnector\n"
    "        if settings.telemetry_executor_url:\n"
    "            executor_client_options: dict[str, str] = {}\n"
    "            if settings.telemetry_secret_region:\n"
    "                executor_client_options[\"region_name\"] = settings.telemetry_secret_region\n"
    "            executor_secrets_client = _LazySecretsManagerClient(\n"
    "                lambda: boto3.client(\"secretsmanager\", **executor_client_options)\n"
    "            )\n"
    "            https_provider = RemoteHttpsTelemetryConnector(\n"
    "                endpoint=settings.telemetry_executor_url,\n"
    "                ca_pem=settings.telemetry_executor_ca_pem,\n"
    "                auth_secret_arn=settings.telemetry_executor_auth_secret_arn,\n"
    "                secret_client=executor_secrets_client,\n"
    "            )\n"
    '        elif settings.app_env in {"prod", "production"}:\n'
    '            raise TelemetryRuntimeUnavailable("telemetry_connector_executor_required")\n'
    "        else:\n"
    "            https_provider = HttpsTelemetryConnector(secret_store=secret_store)\n"
    "\n"
    "        providers = TelemetryProviderRegistry(\n",
)
replace(
    "services/telemetry_runtime.py",
    "                ConnectorType.HTTPS_TELEMETRY: HttpsTelemetryConnector(\n"
    "                    secret_store=secret_store\n"
    "                ),",
    "                ConnectorType.HTTPS_TELEMETRY: https_provider,",
)
