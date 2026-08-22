"""
Pre-flight configuration validator for Easy IMM YAML files.

Scans the merged model for cross-policy references and reports any that
cannot be resolved to a locally defined policy.  This catches problems
*before* Terraform tries its data-source lookups on Intersight, providing
clear, actionable error messages.
"""

from __future__ import annotations

import re
from typing import Any

from yaml_manager import YAMLManager

REFERENCE_SUFFIX_MAP = {
    "multicast_policy": "multicast",
    "flow_control_policy": "flow_control",
    "link_aggregation_policy": "link_aggregation",
    "link_control_policy": "link_control",
    "switch_control_policy": "switch_control",
    "system_qos_policy": "system_qos",
    "ethernet_adapter_policy": "ethernet_adapter",
    "ethernet_network_policy": "ethernet_network",
    "ethernet_network_control_policy": "ethernet_network_control",
    "ethernet_network_group_policy": "ethernet_network_group",
    "ethernet_network_group_policies": "ethernet_network_group",
    "ethernet_qos_policy": "ethernet_qos",
    "fibre_channel_adapter_policy": "fibre_channel_adapter",
    "fibre_channel_network_policy": "fibre_channel_network",
    "fibre_channel_network_policies": "fibre_channel_network",
    "fibre_channel_qos_policy": "fibre_channel_qos",
    "lan_connectivity_policy": "lan_connectivity",
    "san_connectivity_policy": "san_connectivity",
    "bios_policy": "bios",
    "boot_order_policy": "boot_order",
    "firmware_policy": "firmware",
    "imc_access_policy": "imc_access",
    "ipmi_over_lan_policy": "ipmi_over_lan",
    "iscsi_adapter_policy": "iscsi_adapter",
    "ldap_policy": "ldap",
    "local_user_policy": "local_user",
    "memory_policy": "memory",
    "ntp_policy": "ntp",
    "network_connectivity_policy": "network_connectivity",
    "power_policy": "power",
    "scrub_policy": "scrub",
    "serial_over_lan_policy": "serial_over_lan",
    "snmp_policy": "snmp",
    "storage_policy": "storage",
    "thermal_policy": "thermal",
    "virtual_kvm_policy": "virtual_kvm",
    "virtual_media_policy": "virtual_media",
    "sd_card_policy": "sd_card",
    "port_policies": "port",
    "vlan_policies": "vlan",
    "vsan_policies": "vsan",
    "primary_target_policy": "iscsi_static_target",
    "server_pool_qualification_policies": "server_pool_qualification",
}


def _build_policy_index(model: dict) -> dict[str, set[str]]:
    """Build { policy_type: {name1, name2, ...} } from the merged model."""
    index: dict[str, set[str]] = {}
    for org, org_data in model.items():
        if org == "global_settings" or not isinstance(org_data, dict):
            continue
        for category in ("pools", "policies", "profiles", "templates"):
            cat_data = org_data.get(category, {})
            if not isinstance(cat_data, dict):
                continue
            for rtype, resources in cat_data.items():
                if not isinstance(resources, list):
                    continue
                if rtype not in index:
                    index[rtype] = set()
                for r in resources:
                    name = r.get("name")
                    if name:
                        index[rtype].add(name)
                        for o in model:
                            if o != "global_settings":
                                index[rtype].add(f"{o}/{name}")
    return index


def _resolve_ref(ref_value: str, policy_type: str, index: dict[str, set[str]]) -> bool:
    """Check whether a reference value resolves in the index.

    Handles multiple Easy IMM reference formats:
      - ``policyName``
      - ``orgName/policyName``
      - ``policyName (orgName)``
    """
    if not ref_value or not isinstance(ref_value, str):
        return True
    names = index.get(policy_type, set())
    if ref_value in names:
        return True
    bare = ref_value.split("/")[-1] if "/" in ref_value else ref_value
    if bare in names:
        return True
    paren_match = re.match(r"^(.+?)\s*\(([^)]+)\)$", ref_value)
    if paren_match:
        name_part = paren_match.group(1).strip()
        if name_part in names:
            return True
        org_part = paren_match.group(2).strip()
        if f"{org_part}/{name_part}" in names:
            return True
    return False


def _walk_for_refs(
    obj: Any,
    org: str,
    category: str,
    rtype: str,
    resource_name: str,
    index: dict[str, set[str]],
) -> list[dict]:
    """Recursively walk a resource dict/list and check reference fields."""
    issues = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            target_type = REFERENCE_SUFFIX_MAP.get(key)
            if target_type and val:
                ref_values = val if isinstance(val, list) else [val]
                for rv in ref_values:
                    if not isinstance(rv, str) or not rv.strip():
                        continue
                    if not _resolve_ref(rv, target_type, index):
                        issues.append({
                            "level": "error",
                            "org": org,
                            "category": category,
                            "resource_type": rtype,
                            "resource_name": resource_name,
                            "field": key,
                            "ref_value": rv,
                            "expected_type": target_type,
                            "message": (
                                f'{rtype} "{resource_name}" in org "{org}" '
                                f'references {key} "{rv}", but no {target_type} '
                                f'policy named "{rv}" is defined in the workspace.'
                            ),
                        })
            else:
                issues.extend(
                    _walk_for_refs(val, org, category, rtype, resource_name, index)
                )
    elif isinstance(obj, list):
        for item in obj:
            issues.extend(
                _walk_for_refs(item, org, category, rtype, resource_name, index)
            )
    return issues


REQUIRED_NESTED_FIELDS: dict[str, dict[str, list[str]]] = {
    "vlan": {"vlans": ["vlan_list"]},
}


def _check_required_fields(
    resource: dict,
    org: str,
    category: str,
    rtype: str,
    resource_name: str,
) -> list[dict]:
    """Check that nested child objects contain required fields."""
    issues = []
    nested_rules = REQUIRED_NESTED_FIELDS.get(rtype)
    if not nested_rules:
        return issues
    for list_key, required_keys in nested_rules.items():
        children = resource.get(list_key)
        if not isinstance(children, list):
            continue
        for idx, child in enumerate(children):
            if not isinstance(child, dict):
                continue
            child_name = child.get("name", f"item #{idx + 1}")
            for req in required_keys:
                if not child.get(req):
                    issues.append({
                        "level": "error",
                        "org": org,
                        "category": category,
                        "resource_type": rtype,
                        "resource_name": resource_name,
                        "field": req,
                        "ref_value": "",
                        "expected_type": "",
                        "message": (
                            f'{rtype} "{resource_name}" > {list_key} > '
                            f'"{child_name}" in org "{org}" is missing the '
                            f'required field "{req}".'
                        ),
                    })
    return issues


def _collect_dependency_edges(
    model: dict,
    index: dict[str, set[str]],
) -> list[dict]:
    """Find cross-type policy references and build deployment-order warnings.

    The Easy IMM Terraform module is monolithic -- all policies are in a
    single module instance ``module.policies["map"]``.  When policy type A
    references type B, B must already exist on Intersight because the
    module's ``data.tf`` does a live lookup for ALL referenced types in one
    pass.  There is no way to ``-target`` individual policy types.

    The practical workflow is a two-stage apply:
      Stage 1: temporarily strip cross-references, apply standalone policies.
      Stage 2: restore references, apply again so dependent policies link up.
    """
    edges: dict[tuple[str, str], list[str]] = {}

    for org, org_data in model.items():
        if org == "global_settings" or not isinstance(org_data, dict):
            continue
        for category in ("pools", "policies", "profiles", "templates"):
            cat_data = org_data.get(category, {})
            if not isinstance(cat_data, dict):
                continue
            for rtype, resources in cat_data.items():
                if not isinstance(resources, list):
                    continue
                for resource in resources:
                    _collect_edges_from_obj(
                        resource, rtype, resource.get("name", "?"), edges
                    )

    warnings = []
    dep_types = set()
    for (from_type, to_type), examples in sorted(edges.items()):
        if from_type == to_type:
            continue
        dep_types.add(to_type)
        warnings.append({
            "level": "warning",
            "from_type": from_type,
            "to_type": to_type,
            "examples": examples[:3],
            "message": (
                f'"{from_type}" references "{to_type}" policies '
                f'(e.g. {", ".join(examples[:3])}). '
                f'These must exist on Intersight before plan/apply.'
            ),
        })
    return warnings


def _collect_edges_from_obj(
    obj: Any, parent_type: str, resource_name: str,
    edges: dict[tuple[str, str], list[str]],
) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            target = REFERENCE_SUFFIX_MAP.get(key)
            if target and target != parent_type and val:
                pair = (parent_type, target)
                if pair not in edges:
                    edges[pair] = []
                edges[pair].append(resource_name)
            else:
                _collect_edges_from_obj(val, parent_type, resource_name, edges)
    elif isinstance(obj, list):
        for item in obj:
            _collect_edges_from_obj(item, parent_type, resource_name, edges)


def validate_config(yaml_mgr: YAMLManager | None = None) -> dict:
    """Run pre-flight validation and return results.

    Returns ``{"ok": bool, "issues": [...], "deploy_order": [...], "summary": str}``.
    """
    if yaml_mgr is None:
        yaml_mgr = YAMLManager()

    model = yaml_mgr.get_merged_model()
    index = _build_policy_index(model)
    all_issues: list[dict] = []

    for org, org_data in model.items():
        if org == "global_settings" or not isinstance(org_data, dict):
            continue
        for category in ("pools", "policies", "profiles", "templates"):
            cat_data = org_data.get(category, {})
            if not isinstance(cat_data, dict):
                continue
            for rtype, resources in cat_data.items():
                if not isinstance(resources, list):
                    continue
                for resource in resources:
                    name = resource.get("name", "unnamed")
                    issues = _walk_for_refs(
                        resource, org, category, rtype, name, index
                    )
                    all_issues.extend(issues)
                    all_issues.extend(
                        _check_required_fields(resource, org, category, rtype, name)
                    )

    deploy_order = _collect_dependency_edges(model, index)

    if all_issues:
        ref_issues = [i for i in all_issues if i["expected_type"]]
        field_issues = [i for i in all_issues if not i["expected_type"]]
        parts = []
        if ref_issues:
            types = sorted({i["expected_type"] for i in ref_issues})
            parts.append(
                f"{len(ref_issues)} unresolved policy reference(s) for: "
                f"{', '.join(types)}"
            )
        if field_issues:
            fields = sorted({i["field"] for i in field_issues})
            parts.append(
                f"{len(field_issues)} missing required field(s): "
                f"{', '.join(fields)}"
            )
        summary = f"Found {'; '.join(parts)}. Fix these before running Terraform."
    elif deploy_order:
        deps = sorted({w["to_type"] for w in deploy_order})
        summary = (
            f"Config is valid, but deployment order matters. "
            f"Deploy these policy types first: {', '.join(deps)}. "
            f"Then plan/apply the rest."
        )
    else:
        summary = "All policy cross-references and required fields are valid."

    return {
        "ok": len(all_issues) == 0,
        "issues": all_issues,
        "deploy_order": deploy_order,
        "total": len(all_issues),
        "summary": summary,
    }
