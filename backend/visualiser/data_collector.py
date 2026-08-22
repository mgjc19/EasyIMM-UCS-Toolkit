"""
Collects data from the Intersight API and builds the hierarchical tree
used by the visualizer frontend.

Hierarchy:
  Organization
  ├── UCS Domains (fabric.SwitchClusterProfile)
  │   ├── Fabric A / B (fabric.SwitchProfile)
  │   │   └── Per-fabric policies (Port, VLAN, VSAN, …)
  │   └── Domain-level policies (NTP, SNMP, Syslog, …)
  ├── Server Profile Templates
  │   ├── Derived Server Profiles
  │   ├── Compute policies (BIOS, Boot, Firmware, …)
  │   ├── Management policies (IMC Access, KVM, vMedia, …)
  │   ├── Network (LAN Connectivity → vNICs, SAN Connectivity → vHBAs)
  │   └── Storage / Power / Monitoring policies
  └── Chassis Profiles
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .intersight_client import IntersightClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ObjectType → API path mapping
# ---------------------------------------------------------------------------

_PATH_OVERRIDES: dict[str, str] = {
    "bios.Policy": "bios/Policies",
    "boot.PrecisionPolicy": "boot/PrecisionPolicies",
    "access.Policy": "access/Policies",
    "adapter.ConfigPolicy": "adapter/ConfigPolicies",
    "certificatemanagement.Policy": "certificatemanagement/Policies",
    "chassis.Profile": "chassis/Profiles",
    "deviceconnector.Policy": "deviceconnector/Policies",
    "fabric.EthNetworkControlPolicy": "fabric/EthNetworkControlPolicies",
    "fabric.EthNetworkPolicy": "fabric/EthNetworkPolicies",
    "fabric.FcNetworkPolicy": "fabric/FcNetworkPolicies",
    "fabric.FlowControlPolicy": "fabric/FlowControlPolicies",
    "fabric.LinkAggregationPolicy": "fabric/LinkAggregationPolicies",
    "fabric.LinkControlPolicy": "fabric/LinkControlPolicies",
    "fabric.MulticastPolicy": "fabric/MulticastPolicies",
    "fabric.PortPolicy": "fabric/PortPolicies",
    "fabric.SwitchClusterProfile": "fabric/SwitchClusterProfiles",
    "fabric.SwitchControlPolicy": "fabric/SwitchControlPolicies",
    "fabric.SwitchProfile": "fabric/SwitchProfiles",
    "fabric.SystemQosPolicy": "fabric/SystemQosPolicies",
    "fcpool.Pool": "fcpool/Pools",
    "firmware.Policy": "firmware/Policies",
    "iam.EndPointUserPolicy": "iam/EndPointUserPolicies",
    "iam.LdapPolicy": "iam/LdapPolicies",
    "ipmioverlan.Policy": "ipmioverlan/Policies",
    "ippool.Pool": "ippool/Pools",
    "iqnpool.Pool": "iqnpool/Pools",
    "kvm.Policy": "kvm/Policies",
    "macpool.Pool": "macpool/Pools",
    "memory.PersistentMemoryPolicy": "memory/PersistentMemoryPolicies",
    "networkconfig.Policy": "networkconfig/Policies",
    "ntp.Policy": "ntp/Policies",
    "organization.Organization": "organization/Organizations",
    "power.Policy": "power/Policies",
    "resourcepool.Pool": "resourcepool/Pools",
    "sdcard.Policy": "sdcard/Policies",
    "server.Profile": "server/Profiles",
    "server.ProfileTemplate": "server/ProfileTemplates",
    "smtp.Policy": "smtp/Policies",
    "snmp.Policy": "snmp/Policies",
    "sol.Policy": "sol/Policies",
    "ssh.Policy": "ssh/Policies",
    "storage.DriveSecurityPolicy": "storage/DriveSecurityPolicies",
    "storage.StoragePolicy": "storage/StoragePolicies",
    "syslog.Policy": "syslog/Policies",
    "thermal.Policy": "thermal/Policies",
    "uuidpool.Pool": "uuidpool/Pools",
    "vmedia.Policy": "vmedia/Policies",
    "vnic.EthAdapterPolicy": "vnic/EthAdapterPolicies",
    "vnic.EthIf": "vnic/EthIfs",
    "vnic.EthNetworkGroupPolicy": "vnic/EthNetworkGroupPolicies",
    "vnic.EthNetworkPolicy": "vnic/EthNetworkPolicies",
    "vnic.EthQosPolicy": "vnic/EthQosPolicies",
    "vnic.FcAdapterPolicy": "vnic/FcAdapterPolicies",
    "vnic.FcIf": "vnic/FcIfs",
    "vnic.FcNetworkPolicy": "vnic/FcNetworkPolicies",
    "vnic.FcQosPolicy": "vnic/FcQosPolicies",
    "vnic.LanConnectivityPolicy": "vnic/LanConnectivityPolicies",
    "vnic.SanConnectivityPolicy": "vnic/SanConnectivityPolicies",
}


def _object_type_to_path(object_type: str) -> str:
    if object_type in _PATH_OVERRIDES:
        return _PATH_OVERRIDES[object_type]
    parts = object_type.split(".", 1)
    if len(parts) != 2:
        return object_type
    ns, cls = parts
    if cls.endswith("y"):
        plural = cls[:-1] + "ies"
    elif cls.endswith("s"):
        plural = cls + "es"
    else:
        plural = cls + "s"
    return f"{ns}/{plural}"


# ---------------------------------------------------------------------------
# Policy categorization
# ---------------------------------------------------------------------------

POLICY_DISPLAY_NAMES: dict[str, str] = {
    "access.Policy": "IMC Access",
    "adapter.ConfigPolicy": "Adapter Configuration",
    "bios.Policy": "BIOS",
    "boot.PrecisionPolicy": "Boot Order",
    "certificatemanagement.Policy": "Certificate Management",
    "deviceconnector.Policy": "Device Connector",
    "fabric.EthNetworkControlPolicy": "Ethernet Network Control",
    "fabric.EthNetworkPolicy": "VLAN Policy",
    "fabric.FcNetworkPolicy": "VSAN Policy",
    "fabric.FlowControlPolicy": "Flow Control",
    "fabric.LinkAggregationPolicy": "Link Aggregation",
    "fabric.LinkControlPolicy": "Link Control",
    "fabric.MulticastPolicy": "Multicast",
    "fabric.PortPolicy": "Port Policy",
    "fabric.SwitchControlPolicy": "Switch Control",
    "fabric.SystemQosPolicy": "System QoS",
    "firmware.Policy": "Firmware",
    "iam.EndPointUserPolicy": "Local User",
    "iam.LdapPolicy": "LDAP",
    "ipmioverlan.Policy": "IPMI over LAN",
    "kvm.Policy": "KVM",
    "memory.PersistentMemoryPolicy": "Persistent Memory",
    "networkconfig.Policy": "Network Connectivity (DNS)",
    "ntp.Policy": "NTP",
    "power.Policy": "Power",
    "sdcard.Policy": "SD Card",
    "smtp.Policy": "SMTP",
    "snmp.Policy": "SNMP",
    "sol.Policy": "Serial over LAN",
    "ssh.Policy": "SSH",
    "storage.DriveSecurityPolicy": "Drive Security",
    "storage.StoragePolicy": "Storage",
    "syslog.Policy": "Syslog",
    "thermal.Policy": "Thermal",
    "vmedia.Policy": "Virtual Media",
    "vnic.LanConnectivityPolicy": "LAN Connectivity",
    "vnic.SanConnectivityPolicy": "SAN Connectivity",
}

POLICY_CATEGORIES: dict[str, list[str]] = {
    "Compute": [
        "bios.Policy", "boot.PrecisionPolicy", "firmware.Policy",
        "certificatemanagement.Policy",
    ],
    "Management": [
        "access.Policy", "ipmioverlan.Policy", "kvm.Policy", "sol.Policy",
        "vmedia.Policy", "iam.EndPointUserPolicy", "iam.LdapPolicy",
        "ssh.Policy", "deviceconnector.Policy",
    ],
    "Network": [
        "vnic.LanConnectivityPolicy", "vnic.SanConnectivityPolicy",
        "networkconfig.Policy",
    ],
    "Storage": [
        "storage.StoragePolicy", "storage.DriveSecurityPolicy",
        "sdcard.Policy", "memory.PersistentMemoryPolicy",
    ],
    "Power & Thermal": ["power.Policy", "thermal.Policy"],
    "Monitoring": ["snmp.Policy", "syslog.Policy", "smtp.Policy", "ntp.Policy"],
    "Fabric": [
        "fabric.PortPolicy", "fabric.EthNetworkPolicy",
        "fabric.FcNetworkPolicy", "fabric.SwitchControlPolicy",
        "fabric.SystemQosPolicy", "fabric.EthNetworkControlPolicy",
        "fabric.FlowControlPolicy", "fabric.LinkControlPolicy",
        "fabric.LinkAggregationPolicy", "fabric.MulticastPolicy",
    ],
}

_TYPE_TO_CATEGORY: dict[str, str] = {}
for _cat, _types in POLICY_CATEGORIES.items():
    for _t in _types:
        _TYPE_TO_CATEGORY[_t] = _cat


def _get_category(object_type: str) -> str:
    return _TYPE_TO_CATEGORY.get(object_type, "Other")


def _friendly_name(object_type: str) -> str:
    return POLICY_DISPLAY_NAMES.get(object_type, object_type.split(".")[-1])


NODE_COLOURS: dict[str, str] = {
    "root": "#64748b", "organization": "#3b82f6", "group": "#475569",
    "domain_profile": "#8b5cf6", "switch_profile": "#06b6d4",
    "server_profile_template": "#10b981", "server_profile": "#34d399",
    "chassis_profile": "#f59e0b", "policy_category": "#64748b",
    "policy": "#94a3b8", "vnic": "#ec4899", "vhba": "#f43f5e",
    "pool": "#a78bfa",
}

CATEGORY_COLOURS: dict[str, str] = {
    "Compute": "#ef4444", "Management": "#f97316", "Network": "#3b82f6",
    "Storage": "#a855f7", "Power & Thermal": "#eab308",
    "Monitoring": "#14b8a6", "Fabric": "#06b6d4", "Other": "#94a3b8",
}


# ---------------------------------------------------------------------------
# Data fetching helpers
# ---------------------------------------------------------------------------

async def _safe_fetch(coro):
    try:
        return await coro
    except Exception as exc:
        logger.warning("API fetch failed: %s", exc)
        return []


async def _fetch_organizations(client: IntersightClient, org_filter: str | None = None) -> list:
    params: dict[str, str] = {"$orderby": "Name", "$select": "Name,Moid,Description"}
    if org_filter:
        params["$filter"] = f"Name eq '{org_filter}'"
    return await client.get_all("organization/Organizations", params)


async def _fetch_domain_profiles(client: IntersightClient, org_moid: str) -> list:
    return await client.get_all("fabric/SwitchClusterProfiles", {
        "$filter": f"Organization.Moid eq '{org_moid}'",
        "$orderby": "Name",
    })


async def _fetch_switch_profile(client: IntersightClient, moid: str) -> dict:
    return await client.get_by_moid("fabric/SwitchProfiles", moid)


async def _fetch_server_profile_templates(client: IntersightClient, org_moid: str) -> list:
    return await client.get_all("server/ProfileTemplates", {
        "$filter": f"Organization.Moid eq '{org_moid}'",
        "$orderby": "Name",
    })


async def _fetch_server_profiles_for_template(client: IntersightClient, template_moid: str) -> list:
    return await client.get_all("server/Profiles", {
        "$filter": f"SrcTemplate.Moid eq '{template_moid}'",
        "$orderby": "Name",
        "$select": "Name,Moid,Description,AssignedServer,ConfigContext",
    })


async def _fetch_chassis_profiles(client: IntersightClient, org_moid: str) -> list:
    return await client.get_all("chassis/Profiles", {
        "$filter": f"Organization.Moid eq '{org_moid}'",
        "$orderby": "Name",
    })


async def _fetch_vnics(client: IntersightClient, profile_moid: str) -> list:
    return await client.get_all("vnic/EthIfs", {
        "$filter": f"Profile.Moid eq '{profile_moid}'",
        "$orderby": "Order",
    })


async def _fetch_vhbas(client: IntersightClient, profile_moid: str) -> list:
    return await client.get_all("vnic/FcIfs", {
        "$filter": f"Profile.Moid eq '{profile_moid}'",
        "$orderby": "Order",
    })


async def _fetch_policy_names(client: IntersightClient, refs: list[dict]) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    by_type: dict[str, list[str]] = {}

    for ref in refs:
        ot = ref.get("ObjectType", "")
        moid = ref.get("Moid", "")
        if not ot or not moid or moid in lookup:
            continue
        by_type.setdefault(ot, []).append(moid)

    async def _fetch_type(obj_type: str, moids: list[str]):
        api_path = _object_type_to_path(obj_type)
        if len(moids) == 1:
            moid_filter = f"Moid eq '{moids[0]}'"
        else:
            moid_filter = " or ".join(f"Moid eq '{m}'" for m in moids)
        try:
            results = await client.get_all(api_path, {
                "$filter": moid_filter,
                "$select": "Name,Moid,Description,ObjectType",
            })
            for r in results:
                lookup[r["Moid"]] = r
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", obj_type, exc)
            for m in moids:
                lookup[m] = {"Moid": m, "Name": f"({obj_type.split('.')[-1]})", "ObjectType": obj_type}

    tasks = [_fetch_type(ot, moids) for ot, moids in by_type.items()]
    if tasks:
        await asyncio.gather(*tasks)
    return lookup


# ---------------------------------------------------------------------------
# Tree builders
# ---------------------------------------------------------------------------

def _make_node(
    name: str, node_type: str, *, moid: str = "", description: str = "",
    object_type: str = "", children: list | None = None, extra: dict | None = None,
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "name": name, "type": node_type,
        "colour": NODE_COLOURS.get(node_type, "#94a3b8"),
        "children": children if children is not None else [],
    }
    if moid:
        node["moid"] = moid
    if description:
        node["description"] = description
    if object_type:
        node["objectType"] = object_type
    if extra:
        node.update(extra)
    return node


def _policy_refs_to_nodes(refs: list[dict], lookup: dict[str, dict]) -> list[dict]:
    by_category: dict[str, list[dict]] = {}
    for ref in refs:
        ot = ref.get("ObjectType", "")
        moid = ref.get("Moid", "")
        info = lookup.get(moid, {})
        display_name = info.get("Name", _friendly_name(ot))
        category = _get_category(ot)
        cat_colour = CATEGORY_COLOURS.get(category, "#94a3b8")
        pnode = _make_node(
            name=f"{_friendly_name(ot)}: {display_name}", node_type="policy",
            moid=moid, object_type=ot, description=info.get("Description", ""),
            extra={"colour": cat_colour, "category": category},
        )
        by_category.setdefault(category, []).append(pnode)

    result = []
    for cat in ["Compute", "Management", "Network", "Storage",
                "Power & Thermal", "Monitoring", "Fabric", "Other"]:
        if cat in by_category:
            result.append(_make_node(
                cat, "policy_category", children=by_category[cat],
                extra={"colour": CATEGORY_COLOURS.get(cat, "#94a3b8")},
            ))
    return result


async def _build_vnic_children(client: IntersightClient, template_moid: str) -> list[dict]:
    vnics_raw, vhbas_raw = await asyncio.gather(
        _safe_fetch(_fetch_vnics(client, template_moid)),
        _safe_fetch(_fetch_vhbas(client, template_moid)),
    )
    children: list[dict] = []

    if vnics_raw:
        all_sub = []
        for v in vnics_raw:
            for f in ("EthAdapterPolicy", "EthNetworkGroupPolicy", "EthQosPolicy",
                      "FabricEthNetworkControlPolicy", "EthNetworkPolicy", "MacPool"):
                ref = v.get(f)
                if ref and isinstance(ref, dict) and ref.get("Moid"):
                    all_sub.append(ref)
        sub_lookup = await _fetch_policy_names(client, all_sub) if all_sub else {}

        for v in vnics_raw:
            vc: list[dict] = []
            for field, label in [("EthAdapterPolicy", "Adapter Policy"),
                                 ("EthNetworkGroupPolicy", "Network Group Policy"),
                                 ("EthQosPolicy", "QoS Policy"),
                                 ("FabricEthNetworkControlPolicy", "Network Control"),
                                 ("EthNetworkPolicy", "Network Policy"),
                                 ("MacPool", "MAC Pool")]:
                ref = v.get(field)
                if ref and isinstance(ref, dict) and ref.get("Moid"):
                    info = sub_lookup.get(ref["Moid"], {})
                    vc.append(_make_node(
                        f"{label}: {info.get('Name', ref['Moid'][:8])}", "policy",
                        moid=ref.get("Moid", ""), object_type=ref.get("ObjectType", ""),
                        extra={"colour": "#ec4899"},
                    ))
            name = v.get("Name", "vNIC")
            fabric = ""
            pl = v.get("Placement", {})
            if isinstance(pl, dict):
                fabric = pl.get("SwitchId", "")
            lbl = f"vNIC: {name}" + (f" (Fabric {fabric})" if fabric else "")
            children.append(_make_node(lbl, "vnic", moid=v.get("Moid", ""),
                                       object_type="vnic.EthIf", children=vc))

    if vhbas_raw:
        all_sub = []
        for v in vhbas_raw:
            for f in ("FcAdapterPolicy", "FcNetworkPolicy", "FcQosPolicy", "WwpnPool"):
                ref = v.get(f)
                if ref and isinstance(ref, dict) and ref.get("Moid"):
                    all_sub.append(ref)
        sub_lookup = await _fetch_policy_names(client, all_sub) if all_sub else {}

        for v in vhbas_raw:
            vc: list[dict] = []
            for field, label in [("FcAdapterPolicy", "FC Adapter Policy"),
                                 ("FcNetworkPolicy", "FC Network Policy"),
                                 ("FcQosPolicy", "FC QoS Policy"),
                                 ("WwpnPool", "WWPN Pool")]:
                ref = v.get(field)
                if ref and isinstance(ref, dict) and ref.get("Moid"):
                    info = sub_lookup.get(ref["Moid"], {})
                    vc.append(_make_node(
                        f"{label}: {info.get('Name', ref['Moid'][:8])}", "policy",
                        moid=ref.get("Moid", ""), object_type=ref.get("ObjectType", ""),
                        extra={"colour": "#f43f5e"},
                    ))
            name = v.get("Name", "vHBA")
            fabric = ""
            pl = v.get("Placement", {})
            if isinstance(pl, dict):
                fabric = pl.get("SwitchId", "")
            lbl = f"vHBA: {name}" + (f" (Fabric {fabric})" if fabric else "")
            children.append(_make_node(lbl, "vhba", moid=v.get("Moid", ""),
                                       object_type="vnic.FcIf", children=vc))
    return children


async def _build_domain_node(client, domain, policy_lookup):
    node = _make_node(domain["Name"], "domain_profile", moid=domain["Moid"],
                      description=domain.get("Description", ""),
                      object_type="fabric.SwitchClusterProfile")

    sp_refs = domain.get("SwitchProfiles") or []
    sp_tasks = [_safe_fetch(_fetch_switch_profile(client, r["Moid"]))
                for r in sp_refs if r.get("Moid")]
    sps = await asyncio.gather(*sp_tasks) if sp_tasks else []

    for i, sp in enumerate(sps):
        if not sp:
            continue
        fab = "Fabric A" if i == 0 else ("Fabric B" if i == 1 else f"Fabric {i}")
        sp_refs_p = sp.get("PolicyBucket") or []
        if sp_refs_p:
            sl = await _fetch_policy_names(client, sp_refs_p)
            policy_lookup.update(sl)
        node["children"].append(_make_node(
            f"{fab}: {sp.get('Name', 'Switch Profile')}", "switch_profile",
            moid=sp.get("Moid", ""), object_type="fabric.SwitchProfile",
            children=_policy_refs_to_nodes(sp_refs_p, policy_lookup),
            extra={"fabric": fab},
        ))

    dp_refs = domain.get("PolicyBucket") or []
    if dp_refs:
        dl = await _fetch_policy_names(client, dp_refs)
        policy_lookup.update(dl)
        node["children"].append(_make_node(
            "Domain Policies", "policy_category",
            children=_policy_refs_to_nodes(dp_refs, policy_lookup),
            extra={"colour": "#64748b"},
        ))
    return node


async def _build_server_template_node(client, template, policy_lookup):
    node = _make_node(template["Name"], "server_profile_template",
                      moid=template["Moid"],
                      description=template.get("Description", ""),
                      object_type="server.ProfileTemplate")

    derived, vnic_ch = await asyncio.gather(
        _safe_fetch(_fetch_server_profiles_for_template(client, template["Moid"])),
        _safe_fetch(_build_vnic_children(client, template["Moid"])),
    )

    if derived:
        dns = []
        for dp in derived:
            srv = ""
            a = dp.get("AssignedServer")
            if a and isinstance(a, dict):
                srv = a.get("Name", a.get("Moid", "")[:8])
            dns.append(_make_node(dp["Name"], "server_profile", moid=dp["Moid"],
                                  description=dp.get("Description", ""),
                                  object_type="server.Profile",
                                  extra={"assignedServer": srv} if srv else None))
        node["children"].append(_make_node(
            f"Derived Profiles ({len(derived)})", "group",
            children=dns, extra={"colour": "#34d399"}))

    prefs = template.get("PolicyBucket") or []
    if prefs:
        tl = await _fetch_policy_names(client, prefs)
        policy_lookup.update(tl)
        node["children"].extend(_policy_refs_to_nodes(prefs, policy_lookup))

    if vnic_ch:
        node["children"].append(_make_node(
            "NIC / HBA Configuration", "group",
            children=vnic_ch, extra={"colour": "#ec4899"}))
    return node


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

async def build_hierarchy(client: IntersightClient, org_filter: str | None = None) -> dict:
    orgs = await _fetch_organizations(client, org_filter)
    if not orgs:
        return _make_node("Intersight", "root",
                          children=[_make_node("No organizations found", "group")])

    root = _make_node("Intersight", "root")
    root["colours"] = NODE_COLOURS
    root["categoryColours"] = CATEGORY_COLOURS
    root["source"] = "intersight"

    for org in orgs:
        org_node = _make_node(org["Name"], "organization", moid=org["Moid"],
                              description=org.get("Description", ""))
        policy_lookup: dict[str, dict] = {}

        domains, templates, chassis_list = await asyncio.gather(
            _safe_fetch(_fetch_domain_profiles(client, org["Moid"])),
            _safe_fetch(_fetch_server_profile_templates(client, org["Moid"])),
            _safe_fetch(_fetch_chassis_profiles(client, org["Moid"])),
        )

        if domains:
            arefs = []
            for d in domains:
                arefs.extend(d.get("PolicyBucket") or [])
            if arefs:
                policy_lookup.update(await _fetch_policy_names(client, arefs))
            dg = _make_node("UCS Domains", "group",
                            extra={"colour": "#8b5cf6", "icon": "domain"})
            for d in domains:
                dg["children"].append(await _build_domain_node(client, d, policy_lookup))
            org_node["children"].append(dg)

        if templates:
            arefs = []
            for t in templates:
                arefs.extend(t.get("PolicyBucket") or [])
            if arefs:
                policy_lookup.update(await _fetch_policy_names(client, arefs))
            tg = _make_node("Server Profile Templates", "group",
                            extra={"colour": "#10b981", "icon": "template"})
            for t in templates:
                tg["children"].append(await _build_server_template_node(client, t, policy_lookup))
            org_node["children"].append(tg)

        if chassis_list:
            arefs = []
            for c in chassis_list:
                arefs.extend(c.get("PolicyBucket") or [])
            if arefs:
                policy_lookup.update(await _fetch_policy_names(client, arefs))
            cg = _make_node("Chassis Profiles", "group",
                            extra={"colour": "#f59e0b", "icon": "chassis"})
            for c in chassis_list:
                cn = _make_node(c["Name"], "chassis_profile", moid=c["Moid"],
                                description=c.get("Description", ""),
                                object_type="chassis.Profile")
                prefs = c.get("PolicyBucket") or []
                if prefs:
                    cn["children"] = _policy_refs_to_nodes(prefs, policy_lookup)
                cg["children"].append(cn)
            org_node["children"].append(cg)

        root["children"].append(org_node)
    return root


async def fetch_policy_detail(client: IntersightClient, object_type: str, moid: str) -> dict:
    api_path = _object_type_to_path(object_type)
    return await client.get_by_moid(api_path, moid)
