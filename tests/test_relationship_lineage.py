from copy import deepcopy
from types import SimpleNamespace
from app.services.relationship_lineage import issue as _issue, verify
from app.services.phase4_scope import ServerBoundSystemIdentityV2
from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from test_relationship_evidence_binding import raw
from app.services.relationship_evidence_binding import finalize, REGISTRY, resolve, digest


def endpoint(ids=("a", "b"), tenant="tenant-a"):
    authenticated = AuthenticatedPhase4Scope(tenant_scope_id=tenant, workspace_id="workspace")
    return {
        "contract": "relationship-endpoint-identity.v1",
        "scope": {"version": authenticated.version, "tenant_scope_id": tenant,
                  "workspace_id": "workspace", "resource_scope_id": authenticated.resource_scope_id,
                  "system_id": "system", "asset_id": "asset"},
        "mapping_authority_digest": "a" * 64,
        "endpoints": [{"canonical_signal_id": item, "mapping_provenance": [
            {"mapping_id": f"mapping-{item}", "mapping_revision": 1}
        ]} for item in ids],
    }


def observation_lineage(identity):
    return [SimpleNamespace(canonical_signal_id=endpoint["canonical_signal_id"],
                            mapping_id=mapping["mapping_id"], mapping_revision=mapping["mapping_revision"],
                            system_id=identity["scope"]["system_id"], asset_id=identity["scope"]["asset_id"],
                            mapping_authority_digest=identity["mapping_authority_digest"])
            for endpoint in identity["endpoints"] for mapping in endpoint["mapping_provenance"]]


def issue(identity, source, evidence, *, authorized_scope=None, authority=None, asset_id="asset", lineage=None):
    if identity is None:
        return _issue(identity, source, evidence, authorized_scope=authorized_scope)
    if authority is None and len(identity.get("mapping_authority_digest", "")) != 64:
        return _issue(identity, source, evidence, authorized_scope=authorized_scope)
    authority = authority or ServerBoundSystemIdentityV2(
        system_id=identity["scope"]["system_id"],
        resource_scope_id=identity["scope"]["resource_scope_id"],
        authority_record_digest=identity["mapping_authority_digest"],
    )
    authenticated = AuthenticatedPhase4Scope(
        tenant_scope_id=identity["scope"]["tenant_scope_id"],
        workspace_id=identity["scope"]["workspace_id"])
    if authorized_scope is None:
        authorized_scope = digest("relationship-scope.v1", authenticated.as_dict())
    return _issue(identity, source, evidence, authorized_scope=authorized_scope,
                  authenticated_scope=authenticated,
                  phase4_system_identity=authority, asset_id=asset_id,
                  observation_lineage=lineage if lineage is not None else observation_lineage(identity))


def test_symmetric_scope_endpoint_semantics_and_untrusted_fields():
    source = raw()["relationship_source_evidence"]
    evidence = {"basis": "global_relationship_model", "context": {}}
    a = issue(endpoint(), source, evidence)
    assert verify(a)
    assert a["ref"] == issue(endpoint(("b", "a")), source, evidence)["ref"]
    assert a["ref"] != issue(endpoint(("a", "c")), {**source, "columns": ["a", "c"]}, evidence)["ref"]
    assert a["ref"] != issue(endpoint(tenant="tenant-b"), source, evidence)["ref"]
    assert a["ref"] != issue(endpoint(), {**source, "method": "pearson-global.v2"}, evidence)["ref"]
    noisy = deepcopy(source)
    noisy.update(rank=1, primary=True, grouping="x", runtime_id="one", retry_id="one")
    assert issue(endpoint(), noisy, evidence)["ref"] == a["ref"]


def test_basis_mode_and_fallback_are_separate_and_fail_closed():
    source = raw()["relationship_source_evidence"]
    global_ref = issue(endpoint(), source, {"basis": "global_relationship_model", "context": {}})
    mode_source = {**source, "method": "pearson-mode.v1", "selection": {"mode_id": "m1", "features": {"f": "x"}}}
    mode_evidence = {"basis": "mode_conditioned_relationships", "context": {"mode_conditioning": mode_source["selection"]}}
    mode_ref = issue(endpoint(), mode_source, mode_evidence)
    assert mode_ref and mode_ref["ref"] != global_ref["ref"]
    mode_two_source = {**mode_source, "selection": {"mode_id": "m2", "features": {"f": "y"}}}
    mode_two_evidence = {"basis": "mode_conditioned_relationships", "context": {"mode_conditioning": mode_two_source["selection"]}}
    assert issue(endpoint(), mode_two_source, mode_two_evidence)["ref"] != mode_ref["ref"]
    assert issue(endpoint(), {**mode_source, "selection": {"mode_id": "m2", "features": {"f": "x"}}}, mode_evidence) is None
    fallback = issue(endpoint(), source, {"basis": "global_relationship_model_failure_fallback", "context": {}})
    assert fallback and not fallback["continuation_eligible"] and fallback["ref"] != global_ref["ref"]
    assert issue(None, source, {"basis": "global_relationship_model", "context": {}}) is None
    tampered = deepcopy(global_ref)
    tampered["payload"]["assessment_basis"] = "mode_conditioned_relationships"
    assert not verify(tampered)


def test_producer_ref_verifies_and_bad_ref_does_not_resolve():
    source = raw()
    graph = {"edge_basis": "global_relationship_model", "edges": [source]}
    model = {"relationship_graph": {"edges": [source]}, "top_relationship_changes": [deepcopy(source)]}
    identity = endpoint()
    authorized_scope = digest("relationship-scope.v1", {key: identity["scope"][key] for key in (
        "version", "tenant_scope_id", "workspace_id", "resource_scope_id")})
    authority = ServerBoundSystemIdentityV2(system_id="system", resource_scope_id=identity["scope"]["resource_scope_id"],
                                            authority_record_digest="a" * 64)
    authenticated = AuthenticatedPhase4Scope(tenant_scope_id="tenant-a", workspace_id="workspace")
    registry = finalize(model, graph, scope=authorized_scope, endpoint_identity=identity,
                        phase4_system_identity=authority, asset_id="asset", authenticated_scope=authenticated,
                        observation_lineage=observation_lineage(identity))
    assertion = model["top_relationship_changes"][0]
    assert assertion["relationship_lineage_ref"]
    assert resolve(assertion, registry, authorized_scope=authorized_scope)
    assertion["relationship_lineage_ref"] = "relationship-lineage.v1:tampered"
    assert resolve(assertion, registry, authorized_scope=authorized_scope) is None


def test_incomplete_or_tampered_endpoint_map_issues_no_lineage():
    source = raw()["relationship_source_evidence"]
    assert issue(endpoint(("a",)), source, {"basis": "global_relationship_model", "context": {}}) is None
    bad = endpoint()
    bad["mapping_authority_digest"] = ""
    assert issue(bad, source, {"basis": "global_relationship_model", "context": {}}) is None
    bad_provenance = endpoint()
    bad_provenance["endpoints"][0]["mapping_provenance"][0]["mapping_revision"] = 0
    assert issue(bad_provenance, source, {"basis": "global_relationship_model", "context": {}}) is None
    original = endpoint()
    substituted = deepcopy(original)
    substituted["endpoints"][0]["mapping_provenance"][0]["mapping_id"] = "mapping-forged"
    assert issue(substituted, source, {"basis": "global_relationship_model", "context": {}},
                 lineage=observation_lineage(original)) is None
    authenticated = digest("relationship-scope.v1", {key: endpoint()["scope"][key] for key in (
        "version", "tenant_scope_id", "workspace_id", "resource_scope_id")})
    assert issue(endpoint(tenant="tampered"), source,
                 {"basis": "global_relationship_model", "context": {}},
                 authorized_scope=authenticated) is None


def test_phase_a_authority_must_match_mapping_system_asset_and_scope():
    identity = endpoint()
    source = raw()["relationship_source_evidence"]
    evidence = {"basis": "global_relationship_model", "context": {}}
    expected = ServerBoundSystemIdentityV2(system_id="system", resource_scope_id=identity["scope"]["resource_scope_id"],
                                           authority_record_digest="a" * 64)
    tampered = deepcopy(identity)
    tampered["mapping_authority_digest"] = "forged"
    assert issue(tampered, source, evidence, authority=expected) is None
    assert issue(identity, source, evidence, authority=ServerBoundSystemIdentityV2(
        system_id="system", resource_scope_id=identity["scope"]["resource_scope_id"], authority_record_digest="b" * 64)) is None
    assert issue(identity, source, evidence, authority=ServerBoundSystemIdentityV2(
        system_id="other-system", resource_scope_id=identity["scope"]["resource_scope_id"], authority_record_digest="a" * 64)) is None
    assert issue(identity, source, evidence, authority=expected, asset_id="other-asset") is None
    assert issue(identity, source, evidence, authority=expected,
                 authorized_scope="relationship-scope.v1:wrong") is None
    assert issue(identity, {**source, "columns": ["x", "y"]}, evidence, authority=expected) is None


def test_resolve_rechecks_lineage_payload_against_evidence():
    source = raw()
    graph = {"edge_basis": "global_relationship_model", "edges": [source]}
    model = {"relationship_graph": {"edges": [source]}, "top_relationship_changes": [deepcopy(source)]}
    identity = endpoint()
    authorized_scope = digest("relationship-scope.v1", {key: identity["scope"][key] for key in (
        "version", "tenant_scope_id", "workspace_id", "resource_scope_id")})
    authority = ServerBoundSystemIdentityV2(system_id="system", resource_scope_id=identity["scope"]["resource_scope_id"],
                                            authority_record_digest="a" * 64)
    authenticated = AuthenticatedPhase4Scope(tenant_scope_id="tenant-a", workspace_id="workspace")
    registry = finalize(model, graph, scope=authorized_scope, endpoint_identity=identity,
                        phase4_system_identity=authority, asset_id="asset", authenticated_scope=authenticated,
                        observation_lineage=observation_lineage(identity))
    assertion = model["top_relationship_changes"][0]
    assert resolve(assertion, registry, authorized_scope=authorized_scope) is not None

    for field, value in (("endpoints", ["x", "y"]), ("assessment_basis", "mode_conditioned_relationships"),
                         ("semantic_version", "pearson-global.v2"), ("mode_identity", {"mode_id": "forged", "features": {}}),
                         ("scope_ref", "relationship-scope.v1:forged")):
        mutated = deepcopy(registry)
        altered = mutated["relationship_lineage"][assertion["relationship_evidence_ref"]]
        altered["payload"][field] = value
        altered["ref"] = digest("relationship-lineage.v1", altered["payload"])
        assertion["relationship_lineage_ref"] = altered["ref"]
        assert resolve(assertion, mutated, authorized_scope=authorized_scope) is None, field

    assertion.pop("relationship_lineage_ref")
    assert resolve(assertion, registry, authorized_scope=authorized_scope) is not None
