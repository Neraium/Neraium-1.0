"""Infrastructure and certified synthetic read probe; run as a temporary ECS task.

No customer query, data write, connector job, credential print, or result print.
"""
import json
import logging
import os
import ssl
import urllib.request

import psycopg

from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_repository import PostgreSQLTelemetryRepository
from app.services.telemetry_relationship_lineage_v2_repository import PostgreSQLEndpointLineageV2Repository
from app.services.telemetry_endpoint_execution_v2_repository import PostgreSQLEndpointExecutionV2Repository, EndpointExecutionV2Error
from app.services.telemetry_endpoint_result_v2 import list_customer_executions_v2, read_customer_execution_v2

context = ssl.create_default_context(cadata=os.environ["NERAIUM_TELEMETRY_EXECUTOR_CA_PEM"])
with urllib.request.urlopen(os.environ["NERAIUM_TELEMETRY_EXECUTOR_URL"] + "/health", context=context, timeout=8) as response:
    assert response.status == 200 and json.load(response)["status"] == "healthy"

# Exact synthetic identity retained by the Production V2 release certification.
ref = "telemetry-endpoint-execution.v2:10e7a6ab7525950a34494782c701516f707791e9d2894c40d9370f7010659402"


def factory():
    return psycopg.connect(os.environ["NERAIUM_TELEMETRY_DATABASE_URL"], options="-c default_transaction_read_only=on", connect_timeout=8)


with factory() as connection, connection.cursor() as cursor:
    cursor.execute("SELECT resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id, source_run_id FROM telemetry.endpoint_analysis_executions_v2 WHERE execution_ref=%s AND contract_version='telemetry-endpoint-execution.v2'", (ref,))
    row = cursor.fetchone()
assert row is not None
scope = TelemetryScopeRef(resource_scope_id=row[0], tenant_scope_id=row[1], workspace_id=row[2], facility_id=row[3])
repo = PostgreSQLTelemetryRepository(factory)
lineage = PostgreSQLEndpointLineageV2Repository(factory)
executions = PostgreSQLEndpointExecutionV2Repository(factory)
args = dict(repository=repo, lineage_repository=lineage, execution_repository=executions,
            scope=scope, connection_id=str(row[4]), source_run_id=str(row[5]))
items = list_customer_executions_v2(**args, limit=10)
assert any(item["execution_ref"] == ref and item["lineage_verified"] is True for item in items)
detail = read_customer_execution_v2(**args, execution_ref=ref)
assert detail["lineage_verified"] is True
assert detail["result_digest"] == "telemetry-endpoint-result.v2:3bb3fc3d9ff8da1c3dae00108ebbe44de4abd615984ca9953b90b3e1639a56d8"
workspace = "sre-scope-denied"
args["scope"] = TelemetryScopeRef(resource_scope_id=canonical_phase4_resource_scope_id(row[1], workspace), tenant_scope_id=row[1], workspace_id=workspace, facility_id=workspace)
try:
    read_customer_execution_v2(**args, execution_ref=ref)
except EndpointExecutionV2Error:
    pass
else:
    raise AssertionError("foreign_scope_retrieval_allowed")

logging.basicConfig(level=logging.INFO)
from app.routers.data_connections import _record_v2_retrieval_completed
_record_v2_retrieval_completed()
print("production_release_tls_synthetic_v2_scope_pass")
