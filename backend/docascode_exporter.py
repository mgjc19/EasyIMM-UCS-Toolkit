"""
CiscoIQ Document-as-Code exporter.
Maps Easy IMM YAML configs and Redfish server configs into the
data.tech-shared.yaml and data.tech-ucs.yaml format for import
into the CiscoIQ platform.
"""

import json
from pathlib import Path

import yaml as pyyaml


EASYIMM_ROOT = Path(__file__).resolve().parent.parent.parent
REDFISH_WORKSPACE = Path(__file__).resolve().parent.parent / "redfish-workspace"


def _load_redfish_config() -> dict:
    cfg_path = REDFISH_WORKSPACE / "config.json"
    if cfg_path.exists():
        with open(cfg_path) as f:
            return json.load(f)
    return {"server": {}, "resources": {}, "enabled": []}


def _load_easyimm_tree() -> dict:
    """Load and flatten Easy IMM YAML data from all organizations."""
    from yaml_manager import YAMLManager
    mgr = YAMLManager()
    return mgr.get_resource_tree()


def _get_resources(tree: dict, category: str, resource_type: str) -> list:
    """Collect all resources of a type across all orgs.

    Each entry in the tree is { name: str, data: dict }.
    Returns flat list of data dicts with _org injected.
    """
    results = []
    for org_name, cats in tree.items():
        if org_name == "global_settings":
            continue
        for r in cats.get(category, {}).get(resource_type, []):
            if isinstance(r, dict):
                item = dict(r.get("data", {}))
                item["name"] = r.get("name", item.get("name", "unnamed"))
                item["_org"] = org_name
                results.append(item)
    return results


def export_tech_shared(tree: dict = None, redfish_cfg: dict = None) -> dict:
    """
    Generate data.tech-shared.yaml content.
    Maps hardware, cabling, and naming from both Easy IMM and Redfish configurations.
    """
    if tree is None:
        tree = _load_easyimm_tree()
    if redfish_cfg is None:
        redfish_cfg = _load_redfish_config()

    hw_groups = []
    cabling_groups = []
    naming_policies = []
    naming_devices = []

    # -- Hardware from Easy IMM fabric interconnects, chassis, servers --
    fi_devices = []
    for org_name, cats in tree.items():
        for r in cats.get("profiles", {}).get("domain", []):
            d = r.get("data", {}) if isinstance(r, dict) else {}
            fi_devices.append({
                "name": d.get("name", r.get("name", "FI")),
                "model": d.get("model", "UCS Fabric Interconnect"),
                "description": f"Domain profile in org {org_name}",
                "site": org_name,
            })

    if fi_devices:
        hw_groups.append({
            "id": "fabric-interconnects",
            "name": "Fabric Interconnects",
            "role": "Switch",
            "devices": fi_devices,
        })

    chassis_devices = []
    for org_name, cats in tree.items():
        for r in cats.get("profiles", {}).get("chassis", []):
            d = r.get("data", {}) if isinstance(r, dict) else {}
            chassis_devices.append({
                "name": d.get("name", r.get("name", "Chassis")),
                "model": d.get("chassis_model", "UCS Chassis"),
                "description": f"Chassis profile in org {org_name}",
                "site": org_name,
            })

    if chassis_devices:
        hw_groups.append({
            "id": "chassis",
            "name": "UCS Chassis",
            "role": "Server",
            "devices": chassis_devices,
        })

    server_devices = []
    for org_name, cats in tree.items():
        for r in cats.get("profiles", {}).get("server", []):
            d = r.get("data", {}) if isinstance(r, dict) else {}
            server_devices.append({
                "name": d.get("name", r.get("name", "Server")),
                "model": d.get("server_model", "UCS Server"),
                "description": f"Server profile in org {org_name}",
                "site": org_name,
            })

    if server_devices:
        hw_groups.append({
            "id": "servers",
            "name": "UCS Servers",
            "role": "Server",
            "devices": server_devices,
        })

    # -- Hardware from Redfish BMC connection --
    rf_server = redfish_cfg.get("server", {})
    rf_enabled = redfish_cfg.get("enabled", [])
    rf_resources = redfish_cfg.get("resources", {})

    if rf_server.get("endpoint"):
        bmc_modules = []
        if "bmc_network_protocol" in rf_enabled:
            proto_cfg = rf_resources.get("bmc_network_protocol", {})
            services = []
            for svc in ["ssh", "https", "ipmi", "kvmip", "snmp"]:
                if proto_cfg.get(f"{svc}_enabled"):
                    services.append(f"{svc.upper()}:{proto_cfg.get(f'{svc}_port', '')}")
            if services:
                bmc_modules.append({
                    "id": "bmc-services",
                    "description": f"Active services: {', '.join(services)}",
                })

        if "bios" in rf_enabled:
            bios_cfg = rf_resources.get("bios", {})
            attrs = bios_cfg.get("bios_attributes", {})
            if attrs:
                bmc_modules.append({
                    "id": "bios-config",
                    "description": f"BIOS attributes: {len(attrs)} custom settings",
                })

        redfish_device = {
            "name": rf_server.get("endpoint", "").replace("https://", "").replace("http://", ""),
            "model": "Cisco C885A (Redfish-managed)",
            "description": "Redfish-managed bare-metal server",
        }
        if bmc_modules:
            redfish_device["modules"] = bmc_modules

        hw_groups.append({
            "id": "redfish-servers",
            "name": "Redfish Managed Servers",
            "description": "Servers managed via Redfish API / custom Terraform provider",
            "role": "Server",
            "devices": [redfish_device],
        })

    # -- Cabling from Easy IMM port/LAN/SAN policies --
    lan_links = []
    for org_name, cats in tree.items():
        for r in cats.get("policies", {}).get("lan_connectivity", []):
            d = r.get("data", {}) if isinstance(r, dict) else {}
            lan_links.append({
                "from_device": d.get("name", r.get("name", "")),
                "from_port": "vNIC",
                "to_device": "Fabric Interconnect",
                "to_port": "Uplink",
                "cable_type": "Integrated",
                "connector_type": "Integrated",
                "comment": f"LAN connectivity policy ({org_name})",
            })

    if lan_links:
        cabling_groups.append({
            "id": "lan-connectivity",
            "name": "LAN Connectivity",
            "category": "server",
            "links": lan_links,
        })

    san_links = []
    for org_name, cats in tree.items():
        for r in cats.get("policies", {}).get("san_connectivity", []):
            d = r.get("data", {}) if isinstance(r, dict) else {}
            san_links.append({
                "from_device": d.get("name", r.get("name", "")),
                "from_port": "vHBA",
                "to_device": "Fabric Interconnect",
                "to_port": "FC Uplink",
                "cable_type": "Integrated",
                "connector_type": "Integrated",
                "comment": f"SAN connectivity policy ({org_name})",
            })

    if san_links:
        cabling_groups.append({
            "id": "san-connectivity",
            "name": "SAN Connectivity",
            "category": "server",
            "links": san_links,
        })

    # -- Naming conventions from policy names --
    seen = set()
    for org_name, cats in tree.items():
        if org_name == "global_settings":
            continue
        if not isinstance(cats, dict):
            continue
        for cat_name in ("pools", "policies", "profiles", "templates"):
            types_dict = cats.get(cat_name, {})
            if not isinstance(types_dict, dict):
                continue
            for type_name, resources in types_dict.items():
                if not isinstance(resources, list) or not resources:
                    continue
                first_name = resources[0].get("name", "") if isinstance(resources[0], dict) else ""
                if first_name and type_name not in seen:
                    seen.add(type_name)
                    naming_policies.append({
                        "id": type_name,
                        "name": type_name.replace("_", " ").title(),
                        "convention": f"<Org>-{type_name.replace('_', '-').title()}-<Name>",
                        "example": first_name,
                    })

    return {
        "docascode": {
            "tech": {
                "shared": {
                    "hardware": {"groups": hw_groups},
                    "cabling": {"groups": cabling_groups},
                    "naming": {
                        "policies": naming_policies,
                        "devices": naming_devices,
                        "custom": [],
                    },
                }
            }
        }
    }


def export_tech_ucs(tree: dict = None, redfish_cfg: dict = None) -> dict:
    """
    Generate data.tech-ucs.yaml content.
    Maps all Easy IMM resources + Redfish configs to the CiscoIQ tech-ucs schema.
    """
    if tree is None:
        tree = _load_easyimm_tree()
    if redfish_cfg is None:
        redfish_cfg = _load_redfish_config()

    ucs = {}

    # -- Fabrics: derive from org names --
    orgs = list(tree.keys())
    ucs["fabrics"] = [{"name": org, "key": org.lower().replace(" ", "-")} for org in orgs]

    # ═══ Pools ═══
    ucs["mac_pools"] = [
        {
            "name": r.get("name", ""),
            "ucs_domain": r.get("_org", ""),
            "start_address": r.get("data", r).get("from", r.get("data", r).get("mac_blocks", [{}])[0].get("from", "")) if isinstance(r.get("data", r), dict) else "",
            "size": str(r.get("data", r).get("size", "256")),
            "fabric": r.get("data", r).get("assignment_order", "A"),
        }
        for r in _get_resources(tree, "pools", "mac")
    ]

    ucs["mgmt_ip_pools"] = [
        {
            "name": r.get("name", ""),
            "ucs_domain": r.get("_org", ""),
            "start_address": _nested_get(r, "ipv4_blocks", 0, "from", default=""),
            "end_address": _nested_get(r, "ipv4_blocks", 0, "to", default=""),
            "mask": _nested_get(r, "ipv4_configuration", "netmask", default="255.255.255.0"),
            "gateway": _nested_get(r, "ipv4_configuration", "gateway", default=""),
            "primary_dns": _nested_get(r, "ipv4_configuration", "primary_dns", default=""),
            "secondary_dns": _nested_get(r, "ipv4_configuration", "secondary_dns", default=""),
        }
        for r in _get_resources(tree, "pools", "ip")
    ]

    ucs["uuid_pools"] = [
        {
            "name": r.get("name", ""),
            "ucs_domain": r.get("_org", ""),
            "prefix": r.get("prefix", "000025B5-0000-0000"),
            "suffix": _nested_get(r, "uuid_blocks", 0, "from", default=""),
            "size": str(r.get("size", "256")),
        }
        for r in _get_resources(tree, "pools", "uuid")
    ]

    ucs["wwnn_pools"] = [
        {
            "name": r.get("name", ""),
            "ucs_domain": r.get("_org", ""),
            "start_address": _nested_get(r, "id_blocks", 0, "from", default=""),
            "size": str(r.get("size", "256")),
        }
        for r in _get_resources(tree, "pools", "wwnn")
    ]

    ucs["wwpn_pools"] = [
        {
            "name": r.get("name", ""),
            "ucs_domain": r.get("_org", ""),
            "start_address": _nested_get(r, "id_blocks", 0, "from", default=""),
            "size": str(r.get("size", "256")),
            "fabric": r.get("assignment_order", "A"),
        }
        for r in _get_resources(tree, "pools", "wwpn")
    ]

    # ═══ Policies ═══
    bios_resources = _get_resources(tree, "policies", "bios")
    if bios_resources:
        bios_policies = {}
        for i, r in enumerate(bios_resources):
            name = r.get("name", f"BIOS-{i}")
            settings = []
            for k, v in r.items():
                if k.startswith("_") or k == "name" or k == "description" or k == "tags":
                    continue
                if isinstance(v, str) and v != "platform-default":
                    settings.append({"setting": k, "section": "Custom", "value": v})
            key = "esxi" if "esxi" in name.lower() or "vmware" in name.lower() else "hyperv" if "hyper" in name.lower() else f"custom_{i}"
            bios_policies[key] = {"name": name, "settings": settings}
        ucs["bios_policies"] = bios_policies

    boot_resources = _get_resources(tree, "policies", "boot_order")
    if boot_resources:
        ucs["boot_order_policies"] = [
            {
                "name": r.get("name", ""),
                "details": f"Boot Mode: {r.get('boot_mode', 'UEFI')}, Secure Boot: {r.get('enable_secure_boot', 'N/A')}",
            }
            for r in boot_resources
        ]

    ntp_resources = _get_resources(tree, "policies", "ntp")
    if ntp_resources:
        first = ntp_resources[0]
        servers = first.get("ntp_servers", [])
        ucs["ntp_servers"] = servers if isinstance(servers, list) else [servers]
        ucs["ntp_policy"] = {"name": first.get("name", "NTP-Policy"), "enabled": str(first.get("enabled", "Enabled"))}

    snmp_resources = _get_resources(tree, "policies", "snmp")
    if snmp_resources:
        s = snmp_resources[0]
        ucs["snmp"] = {
            "enabled": str(s.get("enabled", "enabled")),
            "hostname": _nested_get(s, "snmp_traps", 0, "destination_address", default=""),
            "community_username": s.get("access_community_string", ""),
            "port": str(s.get("snmp_port", "161")),
            "version": s.get("snmp_engine_input_id", "v2c"),
            "type": "Trap",
        }

    syslog_resources = _get_resources(tree, "policies", "syslog")
    if syslog_resources:
        s = syslog_resources[0]
        ucs["syslog"] = {
            "admin_state": "enabled",
            "level": s.get("local_min_severity", "warnings"),
            "hostname": _nested_get(s, "remote_clients", 0, "hostname", default=""),
        }

    dns_resources = _get_resources(tree, "policies", "network_connectivity")
    if dns_resources:
        d = dns_resources[0]
        servers = d.get("preferred_ipv4_dns_server", "")
        alt = d.get("alternate_ipv4_dns_server", "")
        ucs["dns_servers"] = []
        if servers:
            ucs["dns_servers"].append({"ip_address": servers})
        if alt:
            ucs["dns_servers"].append({"ip_address": alt})
        ucs["network_connectivity_policy"] = {"name": d.get("name", "DNS-Policy")}

    # Server policies
    sol_resources = _get_resources(tree, "policies", "serial_over_lan")
    if sol_resources:
        ucs["serial_over_lan_policies"] = [
            {"name": r.get("name", ""), "enabled": str(r.get("enabled", "Enabled")), "baud_rate": str(r.get("baud_rate", "115200"))}
            for r in sol_resources
        ]

    kvm_resources = _get_resources(tree, "policies", "virtual_kvm")
    if kvm_resources:
        ucs["virtual_kvm_policies"] = [
            {"name": r.get("name", ""), "enable_kvm": str(r.get("enable_virtual_kvm", "Enabled")), "max_sessions": str(r.get("maximum_sessions", "4"))}
            for r in kvm_resources
        ]

    vmedia_resources = _get_resources(tree, "policies", "virtual_media")
    if vmedia_resources:
        ucs["virtual_media_policies"] = [
            {"name": r.get("name", ""), "enable_virtual_media": str(r.get("enable_virtual_media", "Enabled"))}
            for r in vmedia_resources
        ]

    ipmi_resources = _get_resources(tree, "policies", "ipmi_over_lan")
    if ipmi_resources:
        ucs["ipmi_over_lan_policies"] = [
            {"name": r.get("name", ""), "enabled": str(r.get("enabled", "Enabled")), "privilege_level": r.get("privilege", "Admin")}
            for r in ipmi_resources
        ]

    storage_resources = _get_resources(tree, "policies", "storage")
    if storage_resources:
        ucs["storage_policies"] = [
            {
                "name": r.get("name", ""),
                "use_jbod": str(r.get("use_jbod_for_vd_creation", "Disabled")),
                "unused_disks_state": r.get("unused_disks_state", "UnconfiguredGood"),
                "m2_raid_config": str(r.get("m2_virtual_drive", {}).get("enable", "Disabled")) if isinstance(r.get("m2_virtual_drive"), dict) else "Disabled",
            }
            for r in storage_resources
        ]

    lan_resources = _get_resources(tree, "policies", "lan_connectivity")
    if lan_resources:
        ucs["lan_connectivity_policies"] = [
            {"name": r.get("name", ""), "vnic_placement": r.get("target_platform", "Auto")}
            for r in lan_resources
        ]

    san_resources = _get_resources(tree, "policies", "san_connectivity")
    if san_resources:
        ucs["san_connectivity_policies"] = [
            {"name": r.get("name", ""), "wwnn_pool": r.get("wwnn_pool", "")}
            for r in san_resources
        ]

    # Domain policies
    fc_policies = _get_resources(tree, "policies", "flow_control")
    if fc_policies:
        ucs["flow_control_policies"] = [
            {"name": r.get("name", ""), "priority": r.get("priority_enable", "Auto"), "receive_flow_control": r.get("receive", "Disabled"), "send_flow_control": r.get("send", "Disabled")}
            for r in fc_policies
        ]

    la_policies = _get_resources(tree, "policies", "link_aggregation")
    if la_policies:
        ucs["link_aggregation_policies"] = [
            {"name": r.get("name", ""), "suspend_individual": str(r.get("suspend_individual", "Enabled")), "lacp_rate": r.get("lacp_rate", "Normal")}
            for r in la_policies
        ]

    mc_policies = _get_resources(tree, "policies", "multicast")
    if mc_policies:
        ucs["multicast_policies"] = [
            {"name": r.get("name", ""), "snooping_state": str(r.get("snooping_state", "Enabled")), "querier_state": str(r.get("querier_state", "Disabled"))}
            for r in mc_policies
        ]

    thermal_resources = _get_resources(tree, "policies", "thermal")
    if thermal_resources:
        ucs["thermal_policies"] = [
            {"name": r.get("name", ""), "fan_control_mode": r.get("fan_control_mode", "Balanced")}
            for r in thermal_resources
        ]

    power_resources = _get_resources(tree, "policies", "power")
    if power_resources:
        ucs["power_policies"] = [
            {"name": r.get("name", ""), "settings": [{"setting": "Power Redundancy", "value": r.get("power_redundancy", "Grid")}]}
            for r in power_resources
        ]

    imc_resources = _get_resources(tree, "policies", "imc_access")
    if imc_resources:
        ucs["imc_access_policies"] = [
            {"name": r.get("name", ""), "inband_config": f"VLAN: {r.get('inband_vlan_id', 'N/A')}, IP Pool: {r.get('inband_ip_pool', 'N/A')}"}
            for r in imc_resources
        ]

    # ═══ Profiles ═══
    server_profiles = _get_resources(tree, "profiles", "server")
    if server_profiles:
        ucs["server_profiles"] = [
            {"name": r.get("name", ""), "template": r.get("ucs_server_profile_template", "")}
            for r in server_profiles
        ]

    chassis_profiles = _get_resources(tree, "profiles", "chassis")
    if chassis_profiles:
        ucs["chassis_profiles"] = [
            {
                "domain": r.get("_org", ""),
                "chassis": r.get("name", ""),
                "profile_name": r.get("name", ""),
                "profile_template": r.get("ucs_chassis_profile_template", ""),
            }
            for r in chassis_profiles
        ]

    server_templates = _get_resources(tree, "templates", "server")
    if server_templates:
        ucs["service_profile_template_summary"] = [
            {"name": r.get("name", ""), "description": r.get("description", "")}
            for r in server_templates
        ]

    # ═══ Intersight ═══
    ucs["intersight"] = {"management_mode": "cloud (SaaS)"}
    ucs["intersight_organizations"] = [
        {"name": org, "description": f"Organization: {org}", "resource_groups": "All"}
        for org in orgs
    ]

    # ═══ Redfish-sourced data ═══
    rf_enabled = redfish_cfg.get("enabled", [])
    rf_resources = redfish_cfg.get("resources", {})
    rf_server = redfish_cfg.get("server", {})

    if rf_server.get("endpoint"):
        ucs["rack_model"] = "Cisco C885A (Redfish)"

        if "bmc_settings" in rf_enabled:
            bmc = rf_resources.get("bmc_settings", {})
            dns_list = bmc.get("dns_servers", [])
            ntp_list = bmc.get("ntp_servers", [])
            if dns_list:
                if "dns_servers" not in ucs:
                    ucs["dns_servers"] = []
                for d in dns_list:
                    if d and not any(x.get("ip_address") == d for x in ucs["dns_servers"]):
                        ucs["dns_servers"].append({"ip_address": d})
            if ntp_list:
                existing = set(ucs.get("ntp_servers", []))
                ucs["ntp_servers"] = list(existing | set(ntp_list))

        if "bios" in rf_enabled:
            bios = rf_resources.get("bios", {})
            attrs = bios.get("bios_attributes", {})
            if attrs:
                if "bios_policies" not in ucs:
                    ucs["bios_policies"] = {}
                settings = [{"setting": k, "section": "Redfish", "value": str(v)} for k, v in attrs.items()]
                ucs["bios_policies"]["redfish"] = {"name": "Redfish-BIOS", "settings": settings}

        if "boot_order" in rf_enabled:
            boot = rf_resources.get("boot_order", {})
            devices = boot.get("boot_devices", [])
            if devices:
                if "boot_order_policies" not in ucs:
                    ucs["boot_order_policies"] = []
                aliases = ", ".join(d.get("alias", "") for d in devices)
                ucs["boot_order_policies"].append({
                    "name": "Redfish-Boot-Order",
                    "details": f"Boot Devices: {aliases}",
                })

    # Filter empty lists
    ucs = {k: v for k, v in ucs.items() if v or v == 0}

    return {"docascode": {"tech": {"ucs": ucs}}}


def _nested_get(d, *keys, default=""):
    """Safely traverse nested dicts/lists."""
    current = d
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k)
        elif isinstance(current, (list, tuple)) and isinstance(k, int) and k < len(current):
            current = current[k]
        else:
            return default
        if current is None:
            return default
    return current


def export_to_yaml(data: dict) -> str:
    """Serialize to YAML with nice formatting."""
    return pyyaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)
