"""
Intersight-to-EZI-YAML mapper.

Each mapper function takes the ``config`` dict returned by
``_extract_resource(..., full=True)`` and produces a dict that conforms
to the ``.ezi.yaml`` schema consumed by the Easy IMM Terraform modules.

The strategy:
1. Rename Intersight PascalCase keys → Easy IMM snake_case keys.
2. Strip fields whose value equals the module default (avoids noise).
3. Resolve MoRef objects to bare policy/pool names.

Mappers are registered in ``MAPPERS`` keyed by ``(category, resource_type)``.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ref_name(val) -> str:
    """Extract the bare ``name`` from a MoRef-style dict or string."""
    if isinstance(val, dict):
        return val.get("name", "")
    if isinstance(val, str):
        return val
    return ""


def _omit_default(d: dict, key: str, default) -> None:
    """Remove *key* from *d* if its value equals *default*."""
    if d.get(key) == default:
        d.pop(key, None)


def _snake(name: str) -> str:
    """PascalCase / camelCase → snake_case."""
    import re
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _clean_tags(tags) -> list:
    if not isinstance(tags, list):
        return []
    return [t for t in tags if isinstance(t, dict) and (t.get("key") or t.get("value"))]


def _auto_description(name: str, suffix: str) -> str:
    return f"{name} {suffix}."


# ---------------------------------------------------------------------------
# Pool mappers
# ---------------------------------------------------------------------------

def _map_ip_pool(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "IP Pool"):
        out["description"] = desc

    if cfg.get("assignment_order") and cfg["assignment_order"] != "sequential":
        out["assignment_order"] = cfg["assignment_order"]

    v4_blocks = cfg.get("ip_v4_blocks") or []
    v4_config = cfg.get("ip_v4_config") or {}
    if v4_blocks:
        blocks = []
        for b in v4_blocks:
            blk: dict[str, Any] = {"from": b.get("_from", b.get("from", ""))}
            if b.get("to"):
                blk["to"] = b["to"]
            if b.get("size"):
                blk["size"] = b["size"]
            blocks.append(blk)
        out["ipv4_blocks"] = blocks

    if v4_config and v4_config.get("gateway"):
        v4c: dict[str, Any] = {
            "gateway": v4_config["gateway"],
            "netmask": v4_config.get("netmask", ""),
        }
        if v4_config.get("primary_dns"):
            v4c["primary_dns"] = v4_config["primary_dns"]
        if v4_config.get("secondary_dns"):
            v4c["secondary_dns"] = v4_config["secondary_dns"]
        out["ipv4_configuration"] = v4c

    v6_blocks = cfg.get("ip_v6_blocks") or []
    v6_config = cfg.get("ip_v6_config") or {}
    if v6_blocks:
        blocks = []
        for b in v6_blocks:
            blk = {"from": b.get("_from", b.get("from", ""))}
            if b.get("to"):
                blk["to"] = b["to"]
            if b.get("size"):
                blk["size"] = b["size"]
            blocks.append(blk)
        out["ipv6_blocks"] = blocks

    if v6_config and v6_config.get("gateway"):
        v6c: dict[str, Any] = {
            "gateway": v6_config["gateway"],
            "prefix": v6_config.get("prefix", 64),
        }
        if v6_config.get("primary_dns") and v6_config["primary_dns"] != "::":
            v6c["primary_dns"] = v6_config["primary_dns"]
        if v6_config.get("secondary_dns") and v6_config["secondary_dns"] != "::":
            v6c["secondary_dns"] = v6_config["secondary_dns"]
        out["ipv6_configuration"] = v6c

    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_mac_pool(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "MAC Pool"):
        out["description"] = desc
    if cfg.get("assignment_order") and cfg["assignment_order"] != "sequential":
        out["assignment_order"] = cfg["assignment_order"]
    blocks = cfg.get("mac_blocks") or []
    if blocks:
        out["mac_blocks"] = [
            {k: b[k] for k in ("_from", "from", "to", "size") if b.get(k)}
            for b in blocks
        ]
        for blk in out["mac_blocks"]:
            if "_from" in blk:
                blk["from"] = blk.pop("_from")
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_uuid_pool(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "UUID Pool"):
        out["description"] = desc
    if cfg.get("assignment_order") and cfg["assignment_order"] != "sequential":
        out["assignment_order"] = cfg["assignment_order"]
    prefix = cfg.get("prefix", "")
    if prefix and prefix != "000025B5-0000-0000":
        out["prefix"] = prefix
    blocks = cfg.get("uuid_suffix_blocks") or []
    if blocks:
        out["uuid_blocks"] = [
            {k: b[k] for k in ("_from", "from", "to", "size") if b.get(k)}
            for b in blocks
        ]
        for blk in out["uuid_blocks"]:
            if "_from" in blk:
                blk["from"] = blk.pop("_from")
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_iqn_pool(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "IQN Pool"):
        out["description"] = desc
    if cfg.get("assignment_order") and cfg["assignment_order"] != "sequential":
        out["assignment_order"] = cfg["assignment_order"]
    if cfg.get("prefix"):
        out["prefix"] = cfg["prefix"]
    blocks = cfg.get("iqn_suffix_blocks") or []
    if blocks:
        out["iqn_blocks"] = []
        for b in blocks:
            blk: dict[str, Any] = {}
            if b.get("_from") or b.get("from"):
                blk["from"] = b.get("_from", b.get("from"))
            if b.get("to"):
                blk["to"] = b["to"]
            if b.get("size"):
                blk["size"] = b["size"]
            if b.get("suffix") and b["suffix"] != "ucs-host":
                blk["suffix"] = b["suffix"]
            out["iqn_blocks"].append(blk)
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_wwnn_pool(cfg: dict) -> dict:
    return _map_fc_pool(cfg, "WWNN Pool")


def _map_wwpn_pool(cfg: dict) -> dict:
    return _map_fc_pool(cfg, "WWPN Pool")


def _map_fc_pool(cfg: dict, label: str) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], label):
        out["description"] = desc
    if cfg.get("assignment_order") and cfg["assignment_order"] != "sequential":
        out["assignment_order"] = cfg["assignment_order"]
    blocks = cfg.get("id_blocks") or []
    if blocks:
        out["id_blocks"] = [
            {k: b[k] for k in ("_from", "from", "to", "size") if b.get(k)}
            for b in blocks
        ]
        for blk in out["id_blocks"]:
            if "_from" in blk:
                blk["from"] = blk.pop("_from")
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_resource_pool(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Resource Pool"):
        out["description"] = desc
    if cfg.get("pool_type"):
        out["pool_type"] = cfg["pool_type"]
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


# ---------------------------------------------------------------------------
# Policy mappers
# ---------------------------------------------------------------------------

def _map_bios_policy(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "BIOS Policy"):
        out["description"] = desc

    skip = {"name", "description", "tags", "organization"}
    for key, val in cfg.items():
        if key in skip:
            continue
        if isinstance(val, str) and val == "platform-default":
            continue
        if val is None:
            continue
        skey = _snake(key) if not key.islower() else key
        out[skey] = val

    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_boot_order(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Boot Order Policy"):
        out["description"] = desc

    boot_mode = cfg.get("configured_boot_mode", cfg.get("boot_mode", "Uefi"))
    if boot_mode != "Uefi":
        out["boot_mode"] = boot_mode

    secure = cfg.get("enforce_uefi_secure_boot", cfg.get("enable_secure_boot", False))
    if secure:
        out["enable_secure_boot"] = True

    _DEVICE_TYPE_MAP = {
        "boot.FlexMmc": "flex_mmc",
        "boot.Http": "http_boot",
        "boot.Iscsi": "iscsi_boot",
        "boot.LocalCdd": "local_cdd",
        "boot.LocalDisk": "local_disk",
        "boot.Nvme": "nvme",
        "boot.PchStorage": "pch_storage",
        "boot.Pxe": "pxe_boot",
        "boot.San": "san_boot",
        "boot.SdCard": "sd_card",
        "boot.UefiShell": "uefi_shell",
        "boot.Usb": "usb",
        "boot.VirtualMedia": "virtual_media",
    }

    devices = cfg.get("boot_devices") or []
    if devices:
        mapped = []
        for dev in devices:
            d: dict[str, Any] = {
                "device_name": dev.get("name", ""),
                "device_type": _DEVICE_TYPE_MAP.get(
                    dev.get("object_type", ""), dev.get("object_type", "")
                ),
            }
            if dev.get("enabled") is False:
                d["enabled"] = False
            if dev.get("interface_name"):
                d["interface_name"] = dev["interface_name"]
            if dev.get("slot"):
                d["slot"] = dev["slot"]
            if dev.get("sub_type") and dev["sub_type"] != "None":
                d["sub_type"] = dev["sub_type"]
            if dev.get("ip_type") and dev["ip_type"] != "IPv4":
                d["ip_type"] = dev["ip_type"]
            if dev.get("mac_address"):
                d["mac_address"] = dev["mac_address"]
            if dev.get("port") and dev["port"] != -1:
                d["port"] = dev["port"]
            if dev.get("lun") and dev["lun"] != 0:
                d["lun"] = dev["lun"]
            if dev.get("wwpn"):
                d["target_wwpn"] = dev["wwpn"]
            mapped.append(d)
        out["boot_devices"] = mapped

    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_ntp(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "NTP Policy"):
        out["description"] = desc
    if cfg.get("enabled") is False:
        out["enabled"] = False
    servers = cfg.get("ntp_servers") or []
    defaults = ["time-a-g.nist.gov", "time-b-g.nist.gov"]
    if servers and servers != defaults:
        out["ntp_servers"] = servers
    tz = cfg.get("timezone", "")
    if tz and tz != "Etc/GMT":
        out["timezone"] = tz
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_snmp(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "SNMP Policy"):
        out["description"] = desc
    if cfg.get("enabled") is False:
        out["enable_snmp"] = False
    community = cfg.get("community_access", "")
    if community and community != "Disabled":
        out["snmp_community_access"] = community
    if cfg.get("engine_id"):
        out["snmp_engine_input_id"] = cfg["engine_id"]
    port = cfg.get("snmp_port", 161)
    if port != 161:
        out["snmp_port"] = port
    if cfg.get("sys_contact"):
        out["system_contact"] = cfg["sys_contact"]
    if cfg.get("sys_location"):
        out["system_location"] = cfg["sys_location"]

    traps = cfg.get("snmp_traps") or []
    if traps:
        out["snmp_trap_destinations"] = []
        for t in traps:
            td: dict[str, Any] = {"destination_address": t.get("destination", "")}
            if t.get("enabled") is False:
                td["enable"] = False
            if t.get("port", 162) != 162:
                td["port"] = t["port"]
            if t.get("type") and t["type"] != "Trap":
                td["trap_type"] = t["type"]
            if t.get("user"):
                td["user"] = t["user"]
            out["snmp_trap_destinations"].append(td)

    users = cfg.get("snmp_users") or []
    if users:
        out["snmp_users"] = []
        for u in users:
            su: dict[str, Any] = {"name": u.get("name", "")}
            if u.get("auth_type") and u["auth_type"] != "SHA":
                su["auth_type"] = u["auth_type"]
            if u.get("security_level") and u["security_level"] != "AuthPriv":
                su["security_level"] = u["security_level"]
            if u.get("privacy_type") and u["privacy_type"] != "NA":
                su["privacy_type"] = u["privacy_type"]
            out["snmp_users"].append(su)

    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_syslog(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Syslog Policy"):
        out["description"] = desc

    local = cfg.get("local_clients") or []
    if local:
        lc = local[0] if isinstance(local, list) else local
        sev = lc.get("min_severity", "warning")
        if sev != "warning":
            out["local_logging"] = {"minimum_severity": sev}

    remotes = cfg.get("remote_clients") or []
    if remotes:
        rc_out = []
        for rc in remotes:
            r: dict[str, Any] = {}
            if rc.get("enabled") is False:
                r["enable"] = False
            if rc.get("hostname") and rc["hostname"] != "0.0.0.0":
                r["hostname"] = rc["hostname"]
            if rc.get("min_severity") and rc["min_severity"] != "warning":
                r["minimum_severity"] = rc["min_severity"]
            if rc.get("port", 514) != 514:
                r["port"] = rc["port"]
            if rc.get("protocol") and rc["protocol"] != "udp":
                r["protocol"] = rc["protocol"]
            if r:
                rc_out.append(r)
        if rc_out:
            out["remote_logging"] = rc_out

    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_power(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Power Policy"):
        out["description"] = desc

    _RENAMES = {
        "allocated_budget": ("power_allocation", 0),
        "dynamic_rebalancing": ("dynamic_power_rebalancing", "Enabled"),
        "extended_power_capacity": ("extended_power_capacity", "Enabled"),
        "power_priority": ("power_priority", "Low"),
        "power_profiling": ("power_profiling", "Enabled"),
        "power_restore_state": ("power_restore", "LastState"),
        "power_save_mode": ("power_save_mode", "Enabled"),
        "redundancy_mode": ("power_redundancy", "Grid"),
    }
    for api_key, (yaml_key, default) in _RENAMES.items():
        val = cfg.get(api_key)
        if val is not None and val != default:
            out[yaml_key] = val

    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_thermal(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Thermal Policy"):
        out["description"] = desc
    fc = cfg.get("fan_control_mode", "Balanced")
    if fc != "Balanced":
        out["fan_control_mode"] = fc
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_imc_access(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "IMC Access Policy"):
        out["description"] = desc

    vlan = cfg.get("inband_vlan", 0)
    if vlan:
        out["inband_vlan_id"] = vlan

    addr = cfg.get("address_type") or {}
    if addr.get("enable_ip_v4") is False:
        out["ipv4_address_configuration"] = False
    if addr.get("enable_ip_v6") is True:
        out["ipv6_address_configuration"] = True

    inband = cfg.get("inband_ip_pool")
    if inband:
        out["inband_ip_pool"] = _ref_name(inband)
    oob = cfg.get("out_of_band_ip_pool")
    if oob:
        out["out_of_band_ip_pool"] = _ref_name(oob)

    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_ssh(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "SSH Policy"):
        out["description"] = desc
    if cfg.get("enabled") is False:
        out["enabled"] = False
    if cfg.get("port", 22) != 22:
        out["port"] = cfg["port"]
    if cfg.get("timeout", 1800) != 1800:
        out["timeout"] = cfg["timeout"]
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_serial_over_lan(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Serial over LAN Policy"):
        out["description"] = desc
    if cfg.get("enabled") is False:
        out["enabled"] = False
    if cfg.get("baud_rate", 9600) != 9600:
        out["baud_rate"] = cfg["baud_rate"]
    if cfg.get("com_port") and cfg["com_port"] != "com0":
        out["com_port"] = cfg["com_port"]
    if cfg.get("ssh_port", 2400) != 2400:
        out["ssh_port"] = cfg["ssh_port"]
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_virtual_kvm(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Virtual KVM Policy"):
        out["description"] = desc
    if cfg.get("enabled") is False:
        out["enabled"] = False
    if cfg.get("allow_tunneled_kvm") is True:
        out["allow_tunneled_kvm"] = True
    if cfg.get("maximum_sessions", 4) != 4:
        out["maximum_sessions"] = cfg["maximum_sessions"]
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_virtual_media(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Virtual Media Policy"):
        out["description"] = desc
    if cfg.get("enabled") is False:
        out["enabled"] = False
    if cfg.get("encryption") is True:
        out["encryption"] = True
    if cfg.get("low_power_usb") is True:
        out["low_power_usb"] = True
    mappings = cfg.get("mappings") or []
    if mappings:
        out["mappings"] = []
        for m in mappings:
            entry: dict[str, Any] = {"name": m.get("name", "")}
            if m.get("device_type"):
                entry["device_type"] = m["device_type"]
            if m.get("mount_protocol"):
                entry["mount_protocol"] = m["mount_protocol"]
            if m.get("file_location"):
                entry["file_location"] = m["file_location"]
            out["mappings"].append(entry)
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_firmware(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Firmware Policy"):
        out["description"] = desc
    if cfg.get("target_platform"):
        out["target_platform"] = cfg["target_platform"]
    models = cfg.get("model_bundle_combo") or []
    if models:
        out["model_bundle_combo"] = models
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_ipmi_over_lan(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "IPMI over LAN Policy"):
        out["description"] = desc
    if cfg.get("enabled") is False:
        out["enabled"] = False
    if cfg.get("privilege") and cfg["privilege"] != "admin":
        out["privilege"] = cfg["privilege"]
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_network_connectivity(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Network Connectivity Policy"):
        out["description"] = desc
    if cfg.get("preferred_ipv4dns_server"):
        out["preferred_ipv4_dns_server"] = cfg["preferred_ipv4dns_server"]
    if cfg.get("alternate_ipv4dns_server"):
        out["alternate_ipv4_dns_server"] = cfg["alternate_ipv4dns_server"]
    if cfg.get("enable_ipv6") is True:
        out["enable_ipv6"] = True
        if cfg.get("preferred_ipv6dns_server"):
            out["preferred_ipv6_dns_server"] = cfg["preferred_ipv6dns_server"]
        if cfg.get("alternate_ipv6dns_server"):
            out["alternate_ipv6_dns_server"] = cfg["alternate_ipv6dns_server"]
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_adapter_configuration(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Adapter Configuration Policy"):
        out["description"] = desc
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


# --- LAN/SAN connectivity ---

def _map_lan_connectivity(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "LAN Connectivity Policy"):
        out["description"] = desc
    if cfg.get("azure_qos_enabled") is True:
        out["enable_azure_stack_host_qos"] = True
    iqn = cfg.get("iqn_allocation_type", "None")
    if iqn != "None":
        out["iqn_allocation_type"] = iqn
    pool = cfg.get("iqn_pool")
    if pool:
        out["iqn_pool"] = _ref_name(pool)
    if cfg.get("static_iqn_name"):
        out["iqn_static_identifier"] = cfg["static_iqn_name"]
    pm = cfg.get("placement_mode", "custom")
    if pm != "custom":
        out["vnic_placement_mode"] = pm
    tp = cfg.get("target_platform", "FIAttached")
    if tp != "FIAttached":
        out["target_platform"] = tp
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_san_connectivity(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "SAN Connectivity Policy"):
        out["description"] = desc
    wwnn = cfg.get("wwnn_allocation_type", "POOL")
    if wwnn != "POOL":
        out["wwnn_allocation_type"] = wwnn
    pool = cfg.get("wwnn_pool")
    if pool:
        out["wwnn_pool"] = _ref_name(pool)
    tp = cfg.get("target_platform", "FIAttached")
    if tp != "FIAttached":
        out["target_platform"] = tp
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


# --- Ethernet/FC policy stubs ---

def _map_simple_policy(cfg: dict, label: str) -> dict:
    """Fallback mapper that copies name, description, and tags."""
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], label):
        out["description"] = desc
    skip = {"name", "description", "tags", "organization", "moid", "mod_time"}
    for key, val in cfg.items():
        if key in skip or val is None:
            continue
        if isinstance(val, dict) and val.get("class_id") == "mo.MoRef":
            continue
        skey = _snake(key) if not key.islower() else key
        out[skey] = val
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_ethernet_adapter(cfg):
    return _map_simple_policy(cfg, "Ethernet Adapter Policy")


def _map_ethernet_network(cfg):
    return _map_simple_policy(cfg, "Ethernet Network Policy")


def _map_ethernet_network_control(cfg):
    return _map_simple_policy(cfg, "Ethernet Network Control Policy")


def _map_ethernet_network_group(cfg):
    return _map_simple_policy(cfg, "Ethernet Network Group Policy")


def _map_ethernet_qos(cfg):
    return _map_simple_policy(cfg, "Ethernet QoS Policy")


def _map_fibre_channel_adapter(cfg):
    return _map_simple_policy(cfg, "Fibre Channel Adapter Policy")


def _map_fibre_channel_network(cfg):
    return _map_simple_policy(cfg, "Fibre Channel Network Policy")


def _map_fibre_channel_qos(cfg):
    return _map_simple_policy(cfg, "Fibre Channel QoS Policy")


def _map_flow_control(cfg):
    return _map_simple_policy(cfg, "Flow Control Policy")


def _map_link_aggregation(cfg):
    return _map_simple_policy(cfg, "Link Aggregation Policy")


def _map_link_control(cfg):
    return _map_simple_policy(cfg, "Link Control Policy")


def _map_multicast(cfg):
    return _map_simple_policy(cfg, "Multicast Policy")


def _map_switch_control(cfg):
    return _map_simple_policy(cfg, "Switch Control Policy")


def _map_system_qos(cfg):
    return _map_simple_policy(cfg, "System QoS Policy")


def _map_storage(cfg):
    return _map_simple_policy(cfg, "Storage Policy")


def _map_sd_card(cfg):
    return _map_simple_policy(cfg, "SD Card Policy")


def _map_smtp(cfg):
    return _map_simple_policy(cfg, "SMTP Policy")


def _map_local_user(cfg):
    return _map_simple_policy(cfg, "Local User Policy")


def _map_ldap(cfg):
    return _map_simple_policy(cfg, "LDAP Policy")


def _map_port(cfg):
    return _map_simple_policy(cfg, "Port Policy")


# --- VLAN / VSAN ---

def _map_vlan(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    vlan_id = cfg.get("vlan_id")
    if vlan_id is not None:
        out["vlan_list"] = str(vlan_id)
    if cfg.get("is_native") is True:
        out["native_vlan"] = True
    if cfg.get("auto_allow_on_uplinks") is True:
        out["auto_allow_on_uplinks"] = True
    mc = cfg.get("multicast_policy")
    if mc:
        out["multicast_policy"] = _ref_name(mc)
    return out


def _map_vsan(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    if cfg.get("vsan_id"):
        out["vsan_id"] = cfg["vsan_id"]
    dz = cfg.get("default_zoning", "Disabled")
    if dz != "Disabled":
        out["default_zoning"] = dz
    fcoe = cfg.get("fcoe_vlan")
    if fcoe and fcoe != cfg.get("vsan_id"):
        out["fcoe_vlan_id"] = fcoe
    scope = cfg.get("vsan_scope", "Uplink")
    if scope != "Uplink":
        out["vsan_scope"] = scope
    return out


# --- Profiles ---

def _map_server_profile(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Server Profile"):
        out["description"] = desc
    tp = cfg.get("target_platform", "FIAttached")
    if tp != "FIAttached":
        out["target_platform"] = tp

    src = cfg.get("src_template")
    if src:
        out["ucs_server_profile_template"] = _ref_name(src)
    uuid_pool = cfg.get("uuid_pool")
    if uuid_pool:
        out["uuid_pool"] = _ref_name(uuid_pool)
    server_pool = cfg.get("associated_server_pool")
    if server_pool:
        out["resource_pool"] = _ref_name(server_pool)

    bucket = cfg.get("policy_bucket") or []
    _BUCKET_MAP = {
        "bios.Policy": "bios_policy",
        "boot.PrecisionPolicy": "boot_order_policy",
        "access.Policy": "imc_access_policy",
        "power.Policy": "power_policy",
        "thermal.Policy": "thermal_policy",
        "ntp.Policy": "ntp_policy",
        "snmp.Policy": "snmp_policy",
        "syslog.Policy": "syslog_policy",
        "vnic.LanConnectivityPolicy": "lan_connectivity_policy",
        "vnic.SanConnectivityPolicy": "san_connectivity_policy",
        "kvm.Policy": "virtual_kvm_policy",
        "vmedia.Policy": "virtual_media_policy",
        "sol.Policy": "serial_over_lan_policy",
        "ssh.Policy": "ssh_policy",
        "firmware.Policy": "firmware_policy",
        "ipmioverlan.Policy": "ipmi_over_lan_policy",
        "storage.StoragePolicy": "storage_policy",
        "sdcard.Policy": "sd_card_policy",
        "adapter.ConfigPolicy": "adapter_configuration_policy",
    }
    for ref in bucket:
        if isinstance(ref, dict):
            ot = ref.get("object_type", "")
            yaml_key = _BUCKET_MAP.get(ot)
            if yaml_key:
                out[yaml_key] = _ref_name(ref)

    assigned = cfg.get("assigned_server")
    if assigned:
        serial = _ref_name(assigned)
        if serial and serial != "unknown":
            out["serial_number"] = serial

    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_domain_profile(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Domain Profile"):
        out["description"] = desc
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_chassis_profile(cfg: dict) -> dict:
    out: dict[str, Any] = {"name": cfg.get("name", "")}
    desc = cfg.get("description", "")
    if desc and desc != _auto_description(out["name"], "Chassis Profile"):
        out["description"] = desc
    tags = _clean_tags(cfg.get("tags"))
    if tags:
        out["tags"] = tags
    return out


def _map_server_template(cfg: dict) -> dict:
    return _map_server_profile(cfg)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

MAPPERS: dict[tuple[str, str], callable] = {
    # Pools
    ("pools", "ip"): _map_ip_pool,
    ("pools", "mac"): _map_mac_pool,
    ("pools", "uuid"): _map_uuid_pool,
    ("pools", "iqn"): _map_iqn_pool,
    ("pools", "wwnn"): _map_wwnn_pool,
    ("pools", "wwpn"): _map_wwpn_pool,
    ("pools", "resource"): _map_resource_pool,
    # Core policies
    ("policies", "bios"): _map_bios_policy,
    ("policies", "boot_order"): _map_boot_order,
    ("policies", "ntp"): _map_ntp,
    ("policies", "snmp"): _map_snmp,
    ("policies", "syslog"): _map_syslog,
    ("policies", "power"): _map_power,
    ("policies", "thermal"): _map_thermal,
    ("policies", "imc_access"): _map_imc_access,
    ("policies", "ssh"): _map_ssh,
    ("policies", "serial_over_lan"): _map_serial_over_lan,
    ("policies", "virtual_kvm"): _map_virtual_kvm,
    ("policies", "virtual_media"): _map_virtual_media,
    ("policies", "firmware"): _map_firmware,
    ("policies", "ipmi_over_lan"): _map_ipmi_over_lan,
    ("policies", "network_connectivity"): _map_network_connectivity,
    ("policies", "adapter_configuration"): _map_adapter_configuration,
    ("policies", "local_user"): _map_local_user,
    ("policies", "ldap"): _map_ldap,
    # LAN/SAN connectivity
    ("policies", "lan_connectivity"): _map_lan_connectivity,
    ("policies", "san_connectivity"): _map_san_connectivity,
    # Ethernet policies
    ("policies", "ethernet_adapter"): _map_ethernet_adapter,
    ("policies", "ethernet_network"): _map_ethernet_network,
    ("policies", "ethernet_network_control"): _map_ethernet_network_control,
    ("policies", "ethernet_network_group"): _map_ethernet_network_group,
    ("policies", "ethernet_qos"): _map_ethernet_qos,
    # Fibre Channel policies
    ("policies", "fibre_channel_adapter"): _map_fibre_channel_adapter,
    ("policies", "fibre_channel_network"): _map_fibre_channel_network,
    ("policies", "fibre_channel_qos"): _map_fibre_channel_qos,
    # Domain/Fabric policies
    ("policies", "flow_control"): _map_flow_control,
    ("policies", "link_aggregation"): _map_link_aggregation,
    ("policies", "link_control"): _map_link_control,
    ("policies", "multicast"): _map_multicast,
    ("policies", "switch_control"): _map_switch_control,
    ("policies", "system_qos"): _map_system_qos,
    ("policies", "port"): _map_port,
    # VLAN/VSAN
    ("policies", "vlan"): _map_vlan,
    ("policies", "vsan"): _map_vsan,
    # Storage/other
    ("policies", "storage"): _map_storage,
    ("policies", "sd_card"): _map_sd_card,
    ("policies", "smtp"): _map_smtp,
    # Profiles
    ("profiles", "server"): _map_server_profile,
    ("profiles", "domain"): _map_domain_profile,
    ("profiles", "chassis"): _map_chassis_profile,
    # Templates
    ("templates", "server"): _map_server_template,
}


def map_resource(category: str, resource_type: str, config: dict) -> dict | None:
    """Map an Intersight SDK config dict to Easy IMM YAML format.

    Returns ``None`` if no mapper exists for the given type.
    """
    mapper = MAPPERS.get((category, resource_type))
    if mapper is None:
        logger.warning("No mapper for %s/%s -- skipping", category, resource_type)
        return None
    try:
        return mapper(config)
    except Exception:
        logger.exception("Mapper failed for %s/%s", category, resource_type)
        return None
