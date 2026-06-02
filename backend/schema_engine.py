"""
Schema Engine -- parses easy-imm.json and produces form definitions
for the frontend to render dynamic dialogs.

Key capabilities:
  - Resolves $ref / allOf in the JSON schema
  - Extracts field definitions (type, enum, default, description, required)
  - Groups BIOS tokens by section (parsed from the schema description)
  - Identifies cross-reference fields (policy/pool name references)
"""

import json
import re
from pathlib import Path

from paths import EASYIMM_ROOT

SCHEMA_PATH = EASYIMM_ROOT / "yaml_schema" / "easy-imm.json"

CATEGORY_MAP = {
    "pools": [
        "ip", "iqn", "mac", "resource", "uuid", "wwnn", "wwpn",
    ],
    "policies": [
        "adapter_configuration", "bios", "boot_order", "certificate_management",
        "device_connector", "drive_security", "ethernet_adapter", "ethernet_network",
        "ethernet_network_control", "ethernet_network_group", "ethernet_qos",
        "fc_zone", "fibre_channel_adapter", "fibre_channel_network", "fibre_channel_qos",
        "firmware", "firmware_authenticate", "flow_control", "imc_access",
        "ipmi_over_lan", "iscsi_adapter", "iscsi_boot", "iscsi_static_target",
        "lan_connectivity", "ldap", "link_aggregation", "link_control",
        "local_user", "mac_sec", "memory", "multicast", "network_connectivity",
        "ntp", "persistent_memory", "port", "power", "san_connectivity",
        "scrub", "sd_card", "serial_over_lan", "server_pool_qualification",
        "smtp", "snmp", "ssh", "storage", "switch_control", "syslog",
        "system_qos", "thermal", "vhba_template", "virtual_kvm", "virtual_media",
        "vlan", "vnic_template", "vsan",
    ],
    "profiles": ["chassis", "domain", "server"],
    "templates": ["chassis", "domain", "server"],
}

FRIENDLY_NAMES = {
    "ip": "IP Pool", "iqn": "IQN Pool", "mac": "MAC Pool",
    "resource": "Resource Pool", "uuid": "UUID Pool",
    "wwnn": "WWNN Pool", "wwpn": "WWPN Pool",
    "adapter_configuration": "Adapter Configuration",
    "bios": "BIOS", "boot_order": "Boot Order",
    "certificate_management": "Certificate Management",
    "device_connector": "Device Connector",
    "drive_security": "Drive Security",
    "ethernet_adapter": "Ethernet Adapter",
    "ethernet_network": "Ethernet Network",
    "ethernet_network_control": "Ethernet Network Control",
    "ethernet_network_group": "Ethernet Network Group",
    "ethernet_qos": "Ethernet QoS", "fc_zone": "FC Zone",
    "fibre_channel_adapter": "Fibre Channel Adapter",
    "fibre_channel_network": "Fibre Channel Network",
    "fibre_channel_qos": "Fibre Channel QoS",
    "firmware": "Firmware", "firmware_authenticate": "Firmware Authenticate",
    "flow_control": "Flow Control", "imc_access": "IMC Access",
    "ipmi_over_lan": "IPMI Over LAN",
    "iscsi_adapter": "iSCSI Adapter", "iscsi_boot": "iSCSI Boot",
    "iscsi_static_target": "iSCSI Static Target",
    "lan_connectivity": "LAN Connectivity", "ldap": "LDAP",
    "link_aggregation": "Link Aggregation", "link_control": "Link Control",
    "local_user": "Local User", "mac_sec": "MACsec",
    "memory": "Memory", "multicast": "Multicast",
    "network_connectivity": "Network Connectivity",
    "ntp": "NTP", "persistent_memory": "Persistent Memory",
    "port": "Port", "power": "Power",
    "san_connectivity": "SAN Connectivity", "scrub": "Scrub",
    "sd_card": "SD Card", "serial_over_lan": "Serial Over LAN",
    "server_pool_qualification": "Server Pool Qualification",
    "smtp": "SMTP", "snmp": "SNMP", "ssh": "SSH",
    "storage": "Storage", "switch_control": "Switch Control",
    "syslog": "Syslog", "system_qos": "System QoS",
    "thermal": "Thermal", "vhba_template": "vHBA Template",
    "virtual_kvm": "Virtual KVM", "virtual_media": "Virtual Media",
    "vlan": "VLAN", "vnic_template": "vNIC Template", "vsan": "VSAN",
    "chassis": "Chassis", "domain": "Domain", "server": "Server",
}

POLICY_REF_SUFFIXES = ("_policy", "_policies", "_pool", "_pools", "_template")

SECTION_RE = re.compile(r"#\+*\n# (.+?) Section\n#\+*")


class SchemaEngine:
    def __init__(self, schema_path: str | None = None):
        path = Path(schema_path) if schema_path else SCHEMA_PATH
        with open(path, "r") as f:
            self._raw = json.load(f)
        self._schemas = self._raw.get("components", {}).get("schemas", {})
        self._bios_groups = None

    def _resolve_ref(self, ref: str):
        if not ref.startswith("#/"):
            return {}
        parts = ref[2:].split("/")
        node = self._raw
        for p in parts:
            if isinstance(node, dict):
                node = node.get(p, {})
            else:
                return {}
        return node

    def _resolve_schema(self, schema: dict, depth: int = 0) -> dict:
        if depth > 10:
            return schema
        if "$ref" in schema:
            resolved = self._resolve_ref(schema["$ref"])
            return self._resolve_schema(resolved, depth + 1)
        if "allOf" in schema:
            merged = {}
            merged_props = {}
            merged_required = []
            for item in schema["allOf"]:
                resolved = self._resolve_schema(item, depth + 1)
                merged_props.update(resolved.get("properties", {}))
                merged_required.extend(resolved.get("required", []))
                for k, v in resolved.items():
                    if k not in ("properties", "required"):
                        merged[k] = v
            merged["properties"] = merged_props
            if merged_required:
                merged["required"] = list(set(merged_required))
            return merged
        return schema

    def _field_from_property(self, name: str, prop: dict, required_fields: list) -> dict:
        resolved = self._resolve_schema(prop)
        field = {
            "name": name,
            "label": resolved.get("title", name.replace("_", " ").title()),
            "description": resolved.get("description", ""),
            "required": name in required_fields,
            "default": resolved.get("default"),
        }

        if "enum" in resolved:
            field["type"] = "select"
            field["options"] = resolved["enum"]
        elif resolved.get("type") == "boolean":
            field["type"] = "boolean"
        elif resolved.get("type") == "integer":
            field["type"] = "integer"
            if "minimum" in resolved:
                field["minimum"] = resolved["minimum"]
            if "maximum" in resolved:
                field["maximum"] = resolved["maximum"]
        elif resolved.get("type") == "number":
            field["type"] = "number"
        elif resolved.get("type") == "array":
            field["type"] = "array"
            items = resolved.get("items", {})
            resolved_items = self._resolve_schema(items)
            if resolved_items.get("type") == "object":
                field["item_fields"] = self._extract_fields(resolved_items)
            elif "enum" in resolved_items:
                field["item_type"] = "select"
                field["options"] = resolved_items["enum"]
            else:
                field["item_type"] = resolved_items.get("type", "string")
        elif resolved.get("type") == "object":
            field["type"] = "object"
            field["fields"] = self._extract_fields(resolved)
        else:
            field["type"] = "string"
            if resolved.get("pattern"):
                field["pattern"] = resolved["pattern"]

        if any(name.endswith(s) for s in POLICY_REF_SUFFIXES):
            field["is_reference"] = True
            ref_type = None
            for suffix in POLICY_REF_SUFFIXES:
                if name.endswith(suffix):
                    ref_type = name[: -len(suffix)]
                    break
            if ref_type:
                field["ref_resource_type"] = ref_type

        return field

    def _extract_fields(self, schema: dict) -> list:
        props = schema.get("properties", {})
        required = schema.get("required", [])
        fields = []
        for name, prop in props.items():
            fields.append(self._field_from_property(name, prop, required))
        fields.sort(key=lambda f: (not f["required"], f["name"]))
        return fields

    def _parse_bios_groups(self) -> dict[str, list[str]]:
        """Parse BIOS token section groupings from the schema description."""
        if self._bios_groups is not None:
            return self._bios_groups

        bios_schema = self._schemas.get("bios", {})
        all_of = bios_schema.get("allOf", [])

        groups = {}
        for item in all_of:
            desc = item.get("description", "")
            if "# " not in desc:
                continue

            current_section = "General"
            for line in desc.split("\n"):
                stripped = line.strip()
                if stripped.startswith("# ") and stripped.endswith(" Section"):
                    current_section = stripped[2:-8].strip()
                elif stripped.startswith("* "):
                    token_name = stripped[2:].strip()
                    if token_name:
                        groups.setdefault(current_section, []).append(token_name)

        self._bios_groups = groups
        return groups

    def get_resource_schema(self, resource_type: str, category: str) -> dict:
        if category in ("profiles", "templates"):
            schema_key = f"{category}.{resource_type}"
        else:
            schema_key = resource_type

        schema_def = self._schemas.get(schema_key, {})
        if not schema_def:
            return {"type": resource_type, "category": category, "fields": []}

        resolved = self._resolve_schema(schema_def)
        fields = self._extract_fields(resolved)

        result = {
            "type": resource_type,
            "category": category,
            "friendly_name": FRIENDLY_NAMES.get(resource_type, resource_type),
            "fields": fields,
            "description": resolved.get("description", ""),
        }

        if resource_type == "bios":
            result["bios_groups"] = self._parse_bios_groups()

        return result

    def get_all_types(self) -> dict:
        result = {}
        for category, types in CATEGORY_MAP.items():
            result[category] = []
            for t in types:
                result[category].append({
                    "type": t,
                    "friendly_name": FRIENDLY_NAMES.get(t, t),
                })
        return result

    def get_category_map(self) -> dict:
        return CATEGORY_MAP

    def get_reference_types(self) -> dict:
        """Return a mapping of reference field names to the resource types they refer to."""
        ref_map = {}
        for category, types in CATEGORY_MAP.items():
            for t in types:
                for suffix in POLICY_REF_SUFFIXES:
                    ref_map[f"{t}{suffix}"] = {
                        "resource_type": t,
                        "category": "pools" if suffix.endswith("pool") or suffix.endswith("pools") else "policies",
                    }
        return ref_map
