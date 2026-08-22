"""
Parse a UCS techsupport bundle (.tar.gz / .tar) and build the same
hierarchical tree used by the live Intersight visualizer.

Supports both UCSM-mode and Intersight Managed Mode (IMM) bundles.

Hierarchy produced:
  Techsupport: <filename>
  └── Organization (orgOrg)
      ├── Infrastructure
      │   ├── Fabric Interconnects (networkElement)
      │   ├── Chassis (equipmentChassis → computeBlade)
      │   └── Rack Servers (computeRackUnit)
      ├── VLANs / VSANs
      ├── Service Profile Templates (lsServer type=*-template)
      │   ├── Derived Profiles
      │   ├── Attached Policies (by name reference)
      │   └── vNICs / vHBAs (child MOs)
      ├── Standalone Service Profiles
      ├── Policies (grouped by category)
      └── Pools
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import tarfile
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import defusedxml.ElementTree as ET

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MO classes we extract from the bundle
# ---------------------------------------------------------------------------

_INTERESTING_CLASSES: set[str] = {
    # Infrastructure
    "topSystem", "networkElement", "equipmentChassis",
    "computeBlade", "computeRackUnit", "equipmentFex",
    # Organizations
    "orgOrg",
    # Service Profiles / Templates
    "lsServer", "lsServerTemplate",
    # Chassis profiles
    "chassisProfile", "chassisProfileTemplate",
    # Domain profiles (IMM bundles)
    "fabricSwitchProfile", "fabricClusterProfile",
    # Compute policies
    "biosPolicy", "lsbootPolicy", "firmwareComputeHostPack",
    "firmwareChassisPack",
    # Management policies
    "commKvmMgmtPolicy", "cimcvmediaMountConfigPolicy",
    "commGraphicsPolicy", "solPolicy", "solConfig", "solIf",
    "ipmiIf", "commSshPolicy",
    # Network policies
    "vnicLanConnPolicy", "vnicSanConnPolicy",
    "nwctrlDefinition", "epqosDefinition", "fabricQosClass",
    "flowctrlItem", "fabricMulticastPolicy",
    # VLANs / VSANs
    "fabricVlan", "fabricVsan",
    # vNICs / vHBAs and their templates
    "vnicEther", "vnicFc",
    "vnicLanConnTempl", "vnicSanConnTempl",
    # Adapter policies
    "adaptorHostEthIfProfile", "adaptorHostFcIfProfile",
    "adaptorEthCompQueueProfile", "adaptorEthWorkQueueProfile",
    # Storage
    "lstorageProfile", "lstorageDiskGroupConfigPolicy",
    "lstorageDiskGroupQualifier",
    "storageController", "storageLocalDisk",
    # Power / Thermal
    "powerPolicy", "powerGroup", "thermalPolicy",
    # Monitoring
    "commNtpProvider", "commDnsProvider",
    "commSnmp", "commSyslog", "commSmtp",
    # Pools
    "macpoolPool", "macpoolBlock",
    "uuidpoolPool", "uuidpoolBlock",
    "fcpoolInitiators", "fcpoolBlock",
    "ippoolPool", "ippoolBlock", "ippoolIpV6Block",
    "iqnpoolPool", "iqnpoolBlock",
    "resourcepoolPool", "wwpnpoolPool", "wwnnpoolPool",
    # Maintenance
    "lsmaintMaintPolicy",
    # Server management
    "mgmtAccessPolicy",
    # ── Physical view: ports ──
    "fabricEthLanEp", "fabricEthLanPc", "fabricEthLanPcEp",
    "fabricFcSanEp", "fabricFcSanPc",
    "fabricDceSwSrvEp", "fabricDceSwSrvPc", "fabricDceSwSrvPcEp",
    # Physical interface state
    "etherPIo", "fcPIo",
    # Per-port VLAN membership
    "fabricEthVlanPortEp",
    # IOMs / line cards / fans / PSUs
    "equipmentIOCard", "equipmentSwitchCard",
    "equipmentFanModule", "equipmentFan", "equipmentPsu",
    # Physical adapters and interfaces
    "adaptorUnit", "adaptorExtEthIf",
    # CPU / memory
    "processorUnit", "memoryArray", "memoryUnit",
    # CDP / LLDP neighbors
    "networkLanNeighborEntry",
    # Management interface / firmware
    "mgmtIf", "firmwareRunning",
    # ── Faults (for Errors view) ──
    "faultInst",
    # ── Additional Intersight policy classIds ──
    "iamEndPointUserPolicy", "iamLdapPolicy",
    "deviceconnectorPolicy", "adaptorConfigPolicy",
    "fabricPortPolicy", "fabricSwitchControlPolicy",
    "fabricLinkControlPolicy", "fabricLinkAggregationPolicy",
    "fabricEthNetworkPolicy", "fabricFcNetworkPolicy",
    "vnicEthAdapterPolicy", "vnicEthNetworkGroupPolicy",
    "vnicEthQosPolicy", "vnicEthNetworkPolicy",
    "vnicFcAdapterPolicy", "vnicFcQosPolicy", "vnicFcNetworkPolicy",
    "certmgmtPolicy", "storageDriveSecurityPolicy",
    "sdcardPolicy", "memoryPersistentMemoryPolicy",
    "chassisFirmwarePolicy", "fabricSystemQosPolicy",
    "firmwarePolicy", "storagePolicy",
}

# Files to skip (too large / not config data)
_SKIP_PATTERNS: set[str] = {
    "eventlog", "aaadomain", "statshist",
    "sysdebugcore", "sysdebuglog", "fsm", "mostatus",
}

# Intersight ObjectType → UCSM-style classId mapping.
# Intersight techsupport JSON uses "ObjectType" like "organization.Organization"
# while the parser's internal storage uses UCSM-style camelCase classIds.
_INTERSIGHT_OBJ_TYPE_MAP: dict[str, str] = {
    "organization.Organization": "orgOrg",
    # Compute
    "compute.Blade": "computeBlade",
    "compute.RackUnit": "computeRackUnit",
    "equipment.Chassis": "equipmentChassis",
    "equipment.Fex": "equipmentFex",
    "equipment.IoCard": "equipmentIOCard",
    "equipment.SwitchCard": "equipmentSwitchCard",
    "equipment.FanModule": "equipmentFanModule",
    "equipment.Fan": "equipmentFan",
    "equipment.Psu": "equipmentPsu",
    "network.Element": "networkElement",
    "top.System": "topSystem",
    # Server / domain profiles
    "server.Profile": "lsServer",
    "server.ProfileTemplate": "lsServerTemplate",
    "chassis.Profile": "chassisProfile",
    "chassis.ProfileTemplate": "chassisProfileTemplate",
    "fabric.SwitchProfile": "fabricSwitchProfile",
    "fabric.SwitchClusterProfile": "fabricClusterProfile",
    # Policies
    "bios.Policy": "biosPolicy",
    "boot.PrecisionPolicy": "lsbootPolicy",
    "firmware.Policy": "firmwareComputeHostPack",
    "firmware.ChassisUpgrade": "firmwareChassisPack",
    "kvm.Policy": "commKvmMgmtPolicy",
    "vmedia.Policy": "cimcvmediaMountConfigPolicy",
    "sol.Policy": "solPolicy",
    "ipmioverlan.Policy": "ipmiIf",
    "ssh.Policy": "commSshPolicy",
    "vnic.LanConnectivityPolicy": "vnicLanConnPolicy",
    "vnic.SanConnectivityPolicy": "vnicSanConnPolicy",
    "networkconfig.Policy": "nwctrlDefinition",
    "fabric.EthNetworkControlPolicy": "nwctrlDefinition",
    "fabric.FlowControlPolicy": "flowctrlItem",
    "fabric.MulticastPolicy": "fabricMulticastPolicy",
    "fabric.QosClass": "fabricQosClass",
    "fabric.SystemQosPolicy": "fabricSystemQosPolicy",
    "storage.Controller": "storageController",
    "storage.PhysicalDisk": "storageLocalDisk",
    # Additional policies (Intersight full set)
    "thermal.Policy": "thermalPolicy",
    "iam.EndPointUserPolicy": "iamEndPointUserPolicy",
    "iam.LdapPolicy": "iamLdapPolicy",
    "deviceconnector.Policy": "deviceconnectorPolicy",
    "adapter.ConfigPolicy": "adaptorConfigPolicy",
    "fabric.PortPolicy": "fabricPortPolicy",
    "fabric.SwitchControlPolicy": "fabricSwitchControlPolicy",
    "fabric.LinkControlPolicy": "fabricLinkControlPolicy",
    "fabric.LinkAggregationPolicy": "fabricLinkAggregationPolicy",
    "fabric.EthNetworkPolicy": "fabricEthNetworkPolicy",
    "fabric.FcNetworkPolicy": "fabricFcNetworkPolicy",
    "vnic.EthAdapterPolicy": "vnicEthAdapterPolicy",
    "vnic.EthNetworkGroupPolicy": "vnicEthNetworkGroupPolicy",
    "vnic.EthQosPolicy": "vnicEthQosPolicy",
    "vnic.FcAdapterPolicy": "vnicFcAdapterPolicy",
    "vnic.FcQosPolicy": "vnicFcQosPolicy",
    "vnic.FcNetworkPolicy": "vnicFcNetworkPolicy",
    "certificatemanagement.Policy": "certmgmtPolicy",
    "storage.DriveSecurityPolicy": "storageDriveSecurityPolicy",
    "sdcard.Policy": "sdcardPolicy",
    "memory.PersistentMemoryPolicy": "memoryPersistentMemoryPolicy",
    "resourcepool.Pool": "resourcepoolPool",
    "wwpnpool.Pool": "wwpnpoolPool",
    "wwnnpool.Pool": "wwnnpoolPool",
    "chassis.FirmwarePolicy": "chassisFirmwarePolicy",
    # VLANs / VSANs
    "fabric.Vlan": "fabricVlan",
    "fabric.Vsan": "fabricVsan",
    # vNIC / vHBA
    "vnic.EthIf": "vnicEther",
    "vnic.FcIf": "vnicFc",
    "vnic.LanConnectivityTemplate": "vnicLanConnTempl",
    "vnic.SanConnectivityTemplate": "vnicSanConnTempl",
    "vnic.EthNetworkPolicy": "vnicEthNetworkPolicy",
    # Adapter
    "adapter.Unit": "adaptorUnit",
    "adapter.ExtEthInterface": "adaptorExtEthIf",
    "adapter.HostEthInterface": "adaptorHostEthIfProfile",
    "adapter.HostFcInterface": "adaptorHostFcIfProfile",
    # Processor
    "processor.Unit": "processorUnit",
    # Storage
    "storage.StoragePolicy": "lstorageProfile",
    "storage.DiskGroupPolicy": "lstorageDiskGroupConfigPolicy",
    # Power
    "power.Policy": "powerPolicy",
    # NTP / DNS / SNMP / Syslog
    "ntp.Policy": "commNtpProvider",
    "snmp.Policy": "commSnmp",
    "syslog.Policy": "commSyslog",
    "smtp.Policy": "commSmtp",
    # Pools
    "macpool.Pool": "macpoolPool",
    "macpool.Block": "macpoolBlock",
    "uuidpool.Pool": "uuidpoolPool",
    "uuidpool.Block": "uuidpoolBlock",
    "fcpool.Pool": "fcpoolInitiators",
    "fcpool.Block": "fcpoolBlock",
    "ippool.Pool": "ippoolPool",
    "ippool.Block": "ippoolBlock",
    "iqnpool.Pool": "iqnpoolPool",
    "iqnpool.Block": "iqnpoolBlock",
    # Physical ports
    "fabric.EthNetworkPort": "fabricEthLanEp",
    "fabric.FcNetworkPort": "fabricFcSanEp",
    "fabric.ServerPort": "fabricDceSwSrvEp",
    "ether.PhysicalPort": "etherPIo",
    "ether.PortChannel": "fabricEthLanPc",
    "fc.PhysicalPort": "fcPIo",
    "fabric.PortChannel": "fabricEthLanPc",
    "fabric.PortOperation": "fabricEthLanEp",
    # VLAN port info
    "network.VlanPortInfo": "fabricEthVlanPortEp",
    # CPU / Memory
    "memory.Array": "memoryArray",
    "memory.Unit": "memoryUnit",
    # Firmware
    "firmware.RunningFirmware": "firmwareRunning",
    # Management
    "management.Interface": "mgmtIf",
    "management.Controller": "mgmtIf",
    "access.Policy": "mgmtAccessPolicy",
    # IOMs / IO Cards
    "equipment.IoCardOperation": "equipmentIOCard",
    # Network elements (only map Element, not ElementSummary to avoid dups)
    "network.DiscoveredNeighbor": "networkLanNeighborEntry",
    "network.Vethernet": "vnicEther",
    "network.Vfc": "vnicFc",
    # Faults
    "cond.Alarm": "faultInst",
    "tam.AdvisoryInstance": "faultInst",
}
# Build reverse set of interesting Intersight ObjectTypes for fast lookup
_INTERSIGHT_OBJ_TYPES: set[str] = set(_INTERSIGHT_OBJ_TYPE_MAP.keys())

# ---------------------------------------------------------------------------
# Policy display names & categories (mirrors data_collector.py)
# ---------------------------------------------------------------------------

_POLICY_DISPLAY: dict[str, str] = {
    # Compute
    "biosPolicy": "BIOS Policy",
    "lsbootPolicy": "Boot Order Policy",
    "firmwareComputeHostPack": "Firmware Policy",
    "firmwareChassisPack": "Chassis Firmware Package",
    "firmwarePolicy": "Firmware Policy",
    "chassisFirmwarePolicy": "Chassis Firmware Policy",
    # Management
    "commKvmMgmtPolicy": "Virtual KVM Policy",
    "cimcvmediaMountConfigPolicy": "Virtual Media Policy",
    "solPolicy": "Serial over LAN Policy",
    "commSshPolicy": "SSH Policy",
    "mgmtAccessPolicy": "IMC Access Policy",
    "lsmaintMaintPolicy": "Maintenance Policy",
    "ipmiIf": "IPMI over LAN Policy",
    "iamEndPointUserPolicy": "Local User Policy",
    "iamLdapPolicy": "LDAP Policy",
    "deviceconnectorPolicy": "Device Connector Policy",
    "certmgmtPolicy": "Certificate Management Policy",
    # Networking
    "vnicLanConnPolicy": "LAN Connectivity Policy",
    "vnicSanConnPolicy": "SAN Connectivity Policy",
    "nwctrlDefinition": "Ethernet Network Control Policy",
    "epqosDefinition": "QoS Policy",
    "flowctrlItem": "Flow Control Policy",
    "fabricMulticastPolicy": "Multicast Policy",
    "vnicEthAdapterPolicy": "Ethernet Adapter Policy",
    "vnicEthNetworkGroupPolicy": "Ethernet Network Group Policy",
    "vnicEthQosPolicy": "Ethernet QoS Policy",
    "vnicEthNetworkPolicy": "Ethernet Network Policy",
    "vnicFcAdapterPolicy": "Fibre Channel Adapter Policy",
    "vnicFcQosPolicy": "Fibre Channel QoS Policy",
    "vnicFcNetworkPolicy": "Fibre Channel Network Policy",
    "fabricEthNetworkPolicy": "VLAN Policy",
    "fabricFcNetworkPolicy": "VSAN Policy",
    "vnicLanConnTempl": "vNIC Template",
    "vnicSanConnTempl": "vHBA Template",
    "fabricLinkControlPolicy": "Link Control Policy",
    "fabricLinkAggregationPolicy": "Link Aggregation Policy",
    # Storage
    "lstorageProfile": "Storage Policy",
    "lstorageDiskGroupConfigPolicy": "Disk Group Policy",
    "storageDriveSecurityPolicy": "Drive Security Policy",
    "sdcardPolicy": "SD Card Policy",
    "storagePolicy": "Storage Policy",
    # Infrastructure
    "adaptorConfigPolicy": "Adapter Configuration Policy",
    "fabricPortPolicy": "Port Policy",
    "fabricSwitchControlPolicy": "Switch Control Policy",
    "fabricSystemQosPolicy": "System QoS Policy",
    # Power & Thermal
    "powerPolicy": "Power Policy",
    "thermalPolicy": "Thermal Policy",
    # Monitoring
    "commNtpProvider": "NTP Policy",
    "commSnmp": "SNMP Policy",
    "commSyslog": "Syslog Policy",
    "commSmtp": "SMTP Policy",
    # Compute - Memory
    "memoryPersistentMemoryPolicy": "Persistent Memory Policy",
    # Profiles
    "lsServer": "Server Profile",
    "lsServerTemplate": "Server Profile Template",
    "chassisProfile": "Chassis Profile",
    "chassisProfileTemplate": "Chassis Profile Template",
    "fabricSwitchProfile": "Switch Profile",
    "fabricClusterProfile": "Domain Profile",
    # Pools
    "macpoolPool": "MAC Pool",
    "uuidpoolPool": "UUID Pool",
    "fcpoolInitiators": "WWPN Pool",
    "ippoolPool": "IP Pool",
    "iqnpoolPool": "IQN Pool",
    "resourcepoolPool": "Resource Pool",
    "wwpnpoolPool": "WWPN Pool",
    "wwnnpoolPool": "WWNN Pool",
}

_POLICY_CATEGORIES: dict[str, list[str]] = {
    "Compute": [
        "biosPolicy", "lsbootPolicy", "firmwareComputeHostPack",
        "firmwarePolicy", "memoryPersistentMemoryPolicy",
    ],
    "Management": [
        "commKvmMgmtPolicy", "cimcvmediaMountConfigPolicy", "solPolicy",
        "commSshPolicy", "mgmtAccessPolicy", "lsmaintMaintPolicy",
        "ipmiIf", "iamEndPointUserPolicy", "iamLdapPolicy",
        "deviceconnectorPolicy", "certmgmtPolicy",
    ],
    "Networking": [
        "vnicLanConnPolicy", "vnicSanConnPolicy", "nwctrlDefinition",
        "epqosDefinition", "flowctrlItem", "fabricMulticastPolicy",
        "vnicEthAdapterPolicy", "vnicEthNetworkGroupPolicy",
        "vnicEthQosPolicy", "vnicEthNetworkPolicy",
        "vnicFcAdapterPolicy", "vnicFcQosPolicy", "vnicFcNetworkPolicy",
        "fabricEthNetworkPolicy", "fabricFcNetworkPolicy",
        "fabricLinkControlPolicy", "fabricLinkAggregationPolicy",
    ],
    "Storage": [
        "lstorageProfile", "lstorageDiskGroupConfigPolicy",
        "storageDriveSecurityPolicy", "sdcardPolicy", "storagePolicy",
    ],
    "Infrastructure": [
        "adaptorConfigPolicy", "fabricPortPolicy",
        "fabricSwitchControlPolicy", "fabricSystemQosPolicy",
    ],
    "Power & Thermal": ["powerPolicy", "thermalPolicy"],
    "Monitoring": ["commNtpProvider", "commSnmp", "commSyslog", "commSmtp"],
}

_CLASS_TO_CAT: dict[str, str] = {}
for _c, _classes in _POLICY_CATEGORIES.items():
    for _cl in _classes:
        _CLASS_TO_CAT[_cl] = _c

_CATEGORY_COLOURS: dict[str, str] = {
    "Compute": "#ef4444",
    "Management": "#f97316",
    "Networking": "#3b82f6",
    "Storage": "#a855f7",
    "Infrastructure": "#64748b",
    "Power & Thermal": "#eab308",
    "Monitoring": "#14b8a6",
    "Pools": "#06b6d4",
    "Profiles": "#10b981",
    "Templates": "#8b5cf6",
    "Other": "#94a3b8",
}

_NODE_COLOURS: dict[str, str] = {
    "root": "#64748b",
    "organization": "#3b82f6",
    "group": "#475569",
    "domain_profile": "#8b5cf6",
    "switch_profile": "#06b6d4",
    "server_profile_template": "#10b981",
    "server_profile": "#34d399",
    "chassis_profile": "#f59e0b",
    "infrastructure": "#64748b",
    "fi": "#06b6d4",
    "chassis": "#f59e0b",
    "blade": "#34d399",
    "rack_server": "#34d399",
    "vlan": "#3b82f6",
    "vsan": "#8b5cf6",
    "policy_category": "#64748b",
    "policy": "#94a3b8",
    "vnic": "#ec4899",
    "vhba": "#f43f5e",
    "pool": "#a78bfa",
    # Physical view types
    "uplink_port": "#22d3ee",
    "server_port": "#a3e635",
    "fc_port": "#c084fc",
    "port_channel": "#67e8f9",
    "iom": "#fb923c",
    "adapter": "#f472b6",
    "cdp_neighbor": "#94a3b8",
    "cpu": "#818cf8",
    "memory": "#34d399",
    "dimm": "#34d399",
    "firmware": "#64748b",
    "psu": "#eab308",
    "fan": "#a3e635",
    "disk": "#fbbf24",
    "storage_controller": "#fbbf24",
    "qos_class": "#94a3b8",
    "disjoint_vlan": "#dc2626",
    # Error view types
    "error_critical": "#dc2626",
    "error_major": "#f97316",
    "error_minor": "#eab308",
    "error_warning": "#64748b",
    "error_info": "#94a3b8",
    "fault": "#94a3b8",
    "action": "#10b981",
    "root_cause": "#f59e0b",
}

# Attributes on lsServer that reference policy names
_PROFILE_POLICY_ATTRS: dict[str, tuple[str, str]] = {
    "biosProfileName": ("biosPolicy", "BIOS Policy"),
    "bootPolicyName": ("lsbootPolicy", "Boot Order Policy"),
    "hostFwPolicyName": ("firmwareComputeHostPack", "Host Firmware Package"),
    "localDiskPolicyName": ("lstorageDiskGroupConfigPolicy", "Local Disk Policy"),
    "maintPolicyName": ("lsmaintMaintPolicy", "Maintenance Policy"),
    "mgmtAccessPolicyName": ("mgmtAccessPolicy", "Management Access"),
    "powerPolicyName": ("powerPolicy", "Power Policy"),
    "solPolicyName": ("solPolicy", "Serial over LAN"),
    "vmediaPolicyName": ("cimcvmediaMountConfigPolicy", "vMedia Policy"),
    "scrubPolicyName": ("scrubPolicy", "Scrub Policy"),
    "kvmMgmtPolicyName": ("commKvmMgmtPolicy", "KVM Policy"),
    "lanConnPolicyName": ("vnicLanConnPolicy", "LAN Connectivity"),
    "sanConnPolicyName": ("vnicSanConnPolicy", "SAN Connectivity"),
}


# ---------------------------------------------------------------------------
# Node helper (same shape as data_collector._make_node)
# ---------------------------------------------------------------------------

def _mo_pn(mo: dict) -> str:
    """Return the best part-number / PID string from an MO."""
    pn = (mo.get("partNumber", "") or mo.get("PartNumber", "") or "").strip()
    pid = (mo.get("pid", "") or mo.get("Pid", "") or "").strip()
    if pn and pid and pn != pid:
        return f"{pid} ({pn})"
    return pid or pn


def _mo_serial(mo: dict) -> str:
    return (mo.get("serial", "") or mo.get("Serial", "") or "").strip()


def _mo_ident_parts(mo: dict) -> list[str]:
    """Return ['PN: ...', 'SN: ...'] strings when available."""
    parts: list[str] = []
    pn = _mo_pn(mo)
    sn = _mo_serial(mo)
    if pn:
        parts.append(f"PN: {pn}")
    if sn:
        parts.append(f"SN: {sn}")
    return parts


def _node(
    name: str,
    node_type: str,
    *,
    children: list | None = None,
    description: str = "",
    extra: dict | None = None,
) -> dict[str, Any]:
    n: dict[str, Any] = {
        "name": name,
        "type": node_type,
        "colour": _NODE_COLOURS.get(node_type, "#94a3b8"),
        "children": children if children is not None else [],
    }
    if description:
        n["description"] = description
    if extra:
        n.update(extra)
    return n


# ---------------------------------------------------------------------------
# DN utilities
# ---------------------------------------------------------------------------

def _safe_int(val: str, default: int = 0) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _expand_vlan_string(vlan_str: str) -> list[str]:
    """Expand a VLAN range string like '1,8,22,70-201,400' into individual IDs."""
    result: list[str] = []
    for part in vlan_str.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-", 1)
            try:
                start, end = int(bounds[0]), int(bounds[1])
                for v in range(start, min(end + 1, start + 4097)):
                    result.append(str(v))
            except (ValueError, IndexError):
                result.append(part)
        else:
            result.append(part)
    return result


def _dn_parent(dn: str) -> str:
    parts = dn.rsplit("/", 1)
    return parts[0] if len(parts) > 1 else ""


def _dn_org(dn: str) -> str:
    """Return the org-… portion of the DN, e.g. 'org-root' or 'org-root/org-Sub'."""
    parts = dn.split("/")
    org_parts = []
    for p in parts:
        if p.startswith("org-"):
            org_parts.append(p)
        else:
            break
    return "/".join(org_parts) if org_parts else "org-root"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class TechSupportParser:
    """Parse one or more UCS techsupport archives into visualizer trees.

    Supports incremental parsing: call parse() for each file, then
    build_trees() once to produce the combined result.
    """

    def __init__(self, on_progress=None):
        self._mos: dict[str, list[dict]] = {}       # classId → [attrs…]
        self._mos_by_dn: dict[str, dict] = {}        # dn → attrs
        self._filenames: list[str] = []
        self._on_progress = on_progress  # callback(message: str)
        # Policy index maps (populated by _build_policy_index)
        self._server_policy_map: dict[str, list[dict]] = {}
        self._chassis_policy_map: dict[str, list[dict]] = {}
        self._fi_policy_map: dict[str, list[dict]] = {}
        self._profile_name_policy_map: dict[str, list[dict]] = {}
        self._server_profile_info: dict[str, dict] = {}
        self._vnic_logical_map: dict[str, dict] = {}
        self._vhba_logical_map: dict[str, dict] = {}
        self._vnic_fallback_logged = False
        self._xml_child_logged: dict[str, bool] = {}
        # Easyimm XML: template-name→policy-refs, profile-name→policy-refs
        self._easyimm_templates: dict[str, dict] = {}
        self._easyimm_profiles: dict[str, dict] = {}
        # All pool MO names (for showing under connectivity policies)
        self._pool_names: dict[str, list[str]] = {}

    def _emit(self, msg: str):
        if self._on_progress:
            try:
                self._on_progress(msg)
            except Exception:
                pass

    @property
    def _filename(self) -> str:
        if not self._filenames:
            return "techsupport"
        if len(self._filenames) == 1:
            return self._filenames[0]
        return f"{len(self._filenames)} files"

    def parse(self, file_path: str, filename: str = "") -> dict:
        """Parse a single techsupport file. MOs are accumulated across
        multiple parse() calls.  Returns build_trees() for convenience."""
        fname = filename or Path(file_path).name
        self._filenames.append(fname)
        lower = fname.lower()

        self._emit(f"Opening {fname}…")
        if lower.endswith(".json.gz") or lower.endswith(".json"):
            self._emit(f"Parsing JSON: {fname}")
            self._parse_json_file(file_path)
        elif lower.endswith(".xml"):
            self._emit(f"Parsing XML: {fname}")
            self._parse_xml(Path(file_path))
        else:
            with tempfile.TemporaryDirectory() as tmpdir:
                self._emit(f"Extracting archive: {fname}")
                extracted = self._extract_archive_files(file_path, tmpdir)
                xml_files = [p for p in extracted if p.name.lower().endswith(".xml")]
                json_files = [p for p in extracted
                              if p.name.lower().endswith(".json") or p.name.lower().endswith(".json.gz")]
                logger.info("[%s] Found %d XML + %d JSON files in bundle", fname, len(xml_files), len(json_files))
                self._emit(f"Found {len(xml_files)} XML + {len(json_files)} JSON files")

                for i, xp in enumerate(xml_files, 1):
                    self._emit(f"Parsing XML [{i}/{len(xml_files)}]: {xp.name}")
                    self._parse_xml(xp)
                for i, jp in enumerate(json_files, 1):
                    self._emit(f"Parsing JSON [{i}/{len(json_files)}]: {jp.name}")
                    self._parse_json_file(str(jp))

        self._log_summary()
        return self.build_trees()

    def build_trees(self) -> dict:
        """Build all four view trees from the accumulated MOs."""
        self._build_policy_index()
        return {
            "physical": self._build_physical_tree(),
            "logical": self._build_logical_tree(),
            "errors": self._build_errors_tree(),
            "topology": self._build_topology_tree(),
            "source": "techsupport",
            "files": list(self._filenames),
        }

    def _build_policy_index(self):
        """Build lookup maps: server/chassis/FI serial → categorized policy list."""
        # Global Moid → MO lookup for resolving PolicyBucket MoRefs
        self._mo_by_moid: dict[str, dict] = {}
        mo_by_moid = self._mo_by_moid
        for class_id, mos in self._mos.items():
            for mo in mos:
                moid = mo.get("Moid", "")
                if moid:
                    mo_by_moid[moid] = mo

        def _resolve_policies(bucket: list) -> list[dict]:
            """Resolve a PolicyBucket list of MoRefs into policy detail dicts."""
            result = []
            for ref in bucket:
                if not isinstance(ref, dict):
                    continue
                moid = ref.get("Moid", "")
                obj_type = ref.get("ObjectType", "")
                policy_mo = mo_by_moid.get(moid)
                if not policy_mo:
                    continue
                cid = policy_mo.get("_classId", "")
                cat = _CLASS_TO_CAT.get(cid, "Other")
                display = _POLICY_DISPLAY.get(cid, obj_type or cid)
                pname = policy_mo.get("name", policy_mo.get("Name", cid))
                desc_parts = []
                for field in ("descr", "Description"):
                    val = policy_mo.get(field, "")
                    if val:
                        desc_parts.append(val)
                        break
                # Build rich description from policy attributes
                skip = {"_classId", "dn", "Moid", "name", "Name",
                        "ObjectType", "ClassId", "descr", "Description",
                        "_policyBucket", "_AssignedChassis",
                        "AssignedServer", "SrcTemplate",
                        "AccountMoid", "DomainGroupMoid",
                        "SharedScope", "CreateTime", "ModTime",
                        "Ancestors", "PermissionResources", "Tags",
                        "VersionContext", "Organization",
                        "_parent_ctx", "_inherited_switchId"}
                detail_lines = []
                for pk, pv in policy_mo.items():
                    if pk in skip or pk.startswith("_"):
                        continue
                    if isinstance(pv, (str, int, float, bool)) and str(pv):
                        detail_lines.append(f"{pk}: {pv}")
                desc = "\n".join(desc_parts + detail_lines[:40])
                result.append({
                    "category": cat,
                    "type": display,
                    "name": pname,
                    "classId": cid,
                    "moid": moid,
                    "description": desc,
                    "colour": _CATEGORY_COLOURS.get(cat, "#94a3b8"),
                })
            return result

        # Server serial → policies  (from server.Profile)
        self._server_policy_map: dict[str, list[dict]] = {}
        # Also keep a profile-name-based map as fallback
        self._profile_name_policy_map: dict[str, list[dict]] = {}
        # Reverse map: server serial → profile info (name, template, moid)
        self._server_profile_info: dict[str, dict] = {}

        for profile in self._mos.get("lsServer", []):
            prof_name = profile.get("name", profile.get("Name", ""))
            prof_moid = profile.get("Moid", "")

            # Resolve template name if derived from one
            tmpl_name = ""
            src_template = profile.get("SrcTemplate")
            if isinstance(src_template, dict):
                tmpl_moid = src_template.get("Moid", "")
                tmpl_mo = mo_by_moid.get(tmpl_moid)
                if tmpl_mo:
                    tmpl_name = tmpl_mo.get("name", tmpl_mo.get("Name", ""))

            bucket = profile.get("_policyBucket", [])
            policies = _resolve_policies(bucket) if bucket else []
            if policies and prof_name:
                self._profile_name_policy_map[prof_name] = policies

            prof_dn = profile.get("dn", "")
            # UCSM-style: resolve template name from srcTempl attribute
            if not tmpl_name:
                ucsm_tmpl = profile.get("srcTempl", profile.get("operSrcTemplName", ""))
                if ucsm_tmpl:
                    tmpl_name = ucsm_tmpl.rsplit("/", 1)[-1].replace("ls-", "", 1) if "/" in ucsm_tmpl else ucsm_tmpl

            # Easyimm fallback: look up profile name in easyimm data
            if not tmpl_name and prof_name and prof_name in self._easyimm_profiles:
                easyimm_prof = self._easyimm_profiles[prof_name]
                if easyimm_prof.get("template"):
                    tmpl_name = easyimm_prof["template"]

            # Easyimm fallback: match by template name in the easyimm templates list
            if not tmpl_name and prof_name:
                for tname, tdata in self._easyimm_templates.items():
                    if tname in prof_name or prof_name in tname:
                        continue

            info_entry = {
                "name": prof_name,
                "moid": prof_moid,
                "dn": prof_dn,
                "template": tmpl_name,
            }

            # Stamp resolved template back onto the MO for audit checks
            if tmpl_name:
                profile["_resolved_template"] = tmpl_name

            # Try to find assigned server serial — Intersight style (MoRef)
            assigned = profile.get("AssignedServer")
            if isinstance(assigned, dict):
                srv_moid = assigned.get("Moid", "")
                srv_mo = mo_by_moid.get(srv_moid)
                if srv_mo:
                    serial = srv_mo.get("serial", srv_mo.get("Serial", ""))
                    if serial:
                        if policies:
                            self._server_policy_map[serial] = policies
                        self._server_profile_info[serial] = dict(info_entry)
                if srv_moid:
                    if policies:
                        self._server_policy_map.setdefault(srv_moid, policies)
                    self._server_profile_info.setdefault(srv_moid, dict(info_entry))

            # UCSM style: match via pnDn (physical node DN)
            pn_dn = profile.get("pnDn", profile.get("assignedToDn", ""))
            if pn_dn and pn_dn != "":
                for blade in self._mos.get("computeBlade", []):
                    blade_dn = blade.get("dn", "")
                    if blade_dn and blade_dn == pn_dn:
                        serial = blade.get("serial", blade.get("Serial", ""))
                        if serial:
                            if policies:
                                self._server_policy_map.setdefault(serial, policies)
                            self._server_profile_info.setdefault(serial, dict(info_entry))

        # Build vNIC logical definition index: (profile_moid, vnic_name) → policy details
        self._vnic_logical_map: dict[str, dict] = {}
        for vnic in self._mos.get("vnicEther", []):
            parent_prof = vnic.get("Profile")
            if not isinstance(parent_prof, dict):
                continue
            prof_moid = parent_prof.get("Moid", "")
            vnic_name = vnic.get("name", vnic.get("Name", ""))
            if not prof_moid or not vnic_name:
                continue
            # Resolve the MoRef policy references to names
            info: dict[str, str] = {"name": vnic_name}
            for ref_key, label in (
                ("MacPool", "MAC Pool"),
                ("EthAdapterPolicy", "Eth Adapter Policy"),
                ("EthQosPolicy", "Eth QoS Policy"),
                ("EthNetworkGroupPolicy", "Eth Network Group Policy"),
                ("FabricEthNetworkControlPolicy", "Network Control Policy"),
                ("EthNetworkPolicy", "Eth Network Policy"),
            ):
                ref = vnic.get(ref_key)
                if isinstance(ref, dict):
                    ref_moid = ref.get("Moid", "")
                    ref_mo = mo_by_moid.get(ref_moid)
                    if ref_mo:
                        info[label] = ref_mo.get("name", ref_mo.get("Name", ref_moid))
            cdn = vnic.get("Cdn")
            if isinstance(cdn, dict) and cdn.get("Value"):
                info["CDN"] = cdn["Value"]
            self._vnic_logical_map[f"{prof_moid}:{vnic_name}"] = info

        # Same for vHBA: (profile_moid, vhba_name) → policy details
        self._vhba_logical_map: dict[str, dict] = {}
        for vhba in self._mos.get("vnicFc", []):
            parent_prof = vhba.get("Profile")
            if not isinstance(parent_prof, dict):
                continue
            prof_moid = parent_prof.get("Moid", "")
            vhba_name = vhba.get("name", vhba.get("Name", ""))
            if not prof_moid or not vhba_name:
                continue
            info: dict[str, str] = {"name": vhba_name}
            for ref_key, label in (
                ("FcAdapterPolicy", "FC Adapter Policy"),
                ("FcQosPolicy", "FC QoS Policy"),
                ("FcNetworkPolicy", "FC Network Policy"),
                ("WwpnPool", "WWPN Pool"),
                ("WwnnPool", "WWNN Pool"),
            ):
                ref = vhba.get(ref_key)
                if isinstance(ref, dict):
                    ref_moid = ref.get("Moid", "")
                    ref_mo = mo_by_moid.get(ref_moid)
                    if ref_mo:
                        info[label] = ref_mo.get("name", ref_mo.get("Name", ref_moid))
            self._vhba_logical_map[f"{prof_moid}:{vhba_name}"] = info

        # Chassis serial → policies  (from chassis.Profile)
        self._chassis_policy_map: dict[str, list[dict]] = {}
        for profile in self._mos.get("chassisProfile", []):
            bucket = profile.get("_policyBucket", [])
            if not bucket:
                continue
            policies = _resolve_policies(bucket)
            if not policies:
                continue
            prof_name = profile.get("name", "")
            if prof_name:
                self._profile_name_policy_map[prof_name] = policies
            assigned_list = profile.get("_AssignedChassis", [])
            if isinstance(assigned_list, list):
                for ref in assigned_list:
                    if isinstance(ref, dict):
                        ch_moid = ref.get("Moid", "")
                        ch_mo = mo_by_moid.get(ch_moid)
                        if ch_mo:
                            serial = ch_mo.get("serial", ch_mo.get("Serial", ""))
                            if serial:
                                self._chassis_policy_map[serial] = policies

        # FI serial → policies  (from fabric.SwitchProfile via SwitchClusterProfile)
        self._fi_policy_map: dict[str, list[dict]] = {}
        # Collect cluster profile policies
        for cluster in self._mos.get("fabricClusterProfile", []):
            bucket = cluster.get("_policyBucket", [])
            if not bucket:
                continue
            policies = _resolve_policies(bucket)
            if not policies:
                continue
            prof_name = cluster.get("name", "")
            if prof_name:
                self._profile_name_policy_map[prof_name] = policies
            # Apply cluster policies to all FIs
            for fi in self._mos.get("networkElement", []):
                serial = fi.get("serial", fi.get("Serial", ""))
                if serial:
                    existing = self._fi_policy_map.get(serial, [])
                    self._fi_policy_map[serial] = existing + policies

        # Individual switch profiles
        for swprof in self._mos.get("fabricSwitchProfile", []):
            bucket = swprof.get("_policyBucket", [])
            if not bucket:
                continue
            policies = _resolve_policies(bucket)
            if not policies:
                continue
            prof_name = swprof.get("name", "")
            if prof_name:
                self._profile_name_policy_map[prof_name] = policies

        pool_cids = ["macpoolPool", "uuidpoolPool", "fcpoolInitiators",
                     "ippoolPool", "iqnpoolPool", "resourcepoolPool",
                     "wwpnpoolPool", "wwnnpoolPool"]
        pool_counts = {c: len(self._mos.get(c, [])) for c in pool_cids if self._mos.get(c)}

        # Build pool name index for showing pools under connectivity policies
        self._pool_names = {}
        for pc in pool_cids:
            names = []
            for pmo in self._mos.get(pc, []):
                pname = pmo.get("name", pmo.get("Name", ""))
                if pname:
                    names.append(pname)
            if names:
                self._pool_names[pc] = names

        # Log template resolution info
        templates_found = sum(1 for v in self._server_profile_info.values() if v.get("template"))
        easyimm_tmpls = len(self._easyimm_templates)
        logger.info("Policy index: %d server mappings, %d chassis, %d FI, %d profile-name, "
                     "%d server-profile-info (%d with templates), %d vnic-logical, %d vhba-logical, "
                     "pools: %s, easyimm: %d templates, %d profiles",
                     len(self._server_policy_map), len(self._chassis_policy_map),
                     len(self._fi_policy_map), len(self._profile_name_policy_map),
                     len(self._server_profile_info), templates_found,
                     len(self._vnic_logical_map),
                     len(self._vhba_logical_map), pool_counts or "none",
                     easyimm_tmpls, len(self._easyimm_profiles))

    def _log_summary(self):
        total_mos = sum(len(v) for v in self._mos.values())
        logger.info("Total: %d managed objects across %d classes (from %s)",
                     total_mos, len(self._mos), self._filename)
        self._emit(f"Total: {total_mos} managed objects across {len(self._mos)} classes")
        if self._mos:
            for cls, items in sorted(self._mos.items(), key=lambda x: -len(x[1])):
                logger.info("  %-35s : %d MOs", cls, len(items))
                self._emit(f"  {cls}: {len(items)} MOs")
        else:
            logger.warning("No managed objects found in techsupport bundle(s)")
            self._emit("WARNING: No managed objects found")

    # ---- Extraction ----

    _DATA_EXTS = (".xml", ".json")
    _ARCHIVE_EXTS = (".tar.gz", ".tgz", ".tar", ".zip", ".gz")

    def _extract_archive_files(self, archive_path: str, dest: str) -> list[Path]:
        """Extract data files from archives, recursing into nested archives."""
        extracted: list[Path] = []
        self._extract_recursive(archive_path, dest, extracted, depth=0)
        return extracted

    def _extract_recursive(self, archive_path: str, dest: str,
                           extracted: list[Path], depth: int):
        """Recursively extract archives up to 3 levels deep."""
        if depth > 3:
            return

        lower_path = archive_path.lower()

        # Single gzipped file (not tar.gz)
        if lower_path.endswith(".gz") and not lower_path.endswith(".tar.gz"):
            self._handle_gz_file(archive_path, dest, extracted, depth)
            return

        nested_archives: list[Path] = []

        if tarfile.is_tarfile(archive_path):
            self._extract_from_tar(archive_path, dest, extracted, nested_archives)
        elif zipfile.is_zipfile(archive_path):
            self._extract_from_zip(archive_path, dest, extracted, nested_archives)
        else:
            if depth == 0:
                raise ValueError("Unsupported archive format")
            return

        for nested in nested_archives:
            self._emit(f"  Extracting nested: {nested.name}")
            self._extract_recursive(str(nested), dest, extracted, depth + 1)
            try:
                nested.unlink()
            except OSError:
                pass

    def _handle_gz_file(self, gz_path: str, dest: str,
                        extracted: list[Path], depth: int):
        """Decompress a .gz file. If it contains XML/JSON, keep it.
        If it's a nested archive, recurse."""
        import gzip as _gzip
        base = Path(gz_path).stem
        out = self._unique_path(dest, base)
        try:
            with _gzip.open(gz_path, "rb") as f:
                content = f.read(4 * 1024 * 1024)  # peek 4 MB
                remaining = f.read()
                content += remaining
        except Exception:
            return

        out.write_bytes(content)
        lower_out = out.name.lower()

        if any(lower_out.endswith(ext) for ext in self._DATA_EXTS):
            if not self._should_skip(out.name):
                extracted.append(out)
        elif tarfile.is_tarfile(str(out)):
            self._extract_recursive(str(out), dest, extracted, depth + 1)
            try:
                out.unlink()
            except OSError:
                pass
        else:
            # Might be XML/JSON without the right extension -- sniff content
            head = content[:200].lstrip()
            if head.startswith(b"<?xml") or head.startswith(b"<") or head.startswith(b"{") or head.startswith(b"["):
                ext = ".xml" if head.startswith(b"<") else ".json"
                new_out = out.with_suffix(ext)
                out.rename(new_out)
                if not self._should_skip(new_out.name):
                    extracted.append(new_out)
            else:
                try:
                    out.unlink()
                except OSError:
                    pass

    def _extract_from_tar(self, archive_path: str, dest: str,
                          extracted: list[Path], nested_archives: list[Path]):
        with tarfile.open(archive_path, "r:*") as tar:
            members = tar.getmembers()
            file_members = [m for m in members if m.isfile()]
            ext_counts: dict[str, int] = {}
            for m in file_members:
                ext = self._ext_of(m.name)
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
            logger.info("  Archive contents: %d files %s",
                        len(file_members),
                        dict(sorted(ext_counts.items(), key=lambda x: -x[1])))

            for member in file_members:
                lower_name = member.name.lower()
                basename = os.path.basename(member.name)

                safe_path = os.path.join(dest, basename)
                if not os.path.realpath(safe_path).startswith(os.path.realpath(dest)):
                    continue

                is_data = any(lower_name.endswith(ext) for ext in self._DATA_EXTS)
                is_archive = any(lower_name.endswith(ext) for ext in self._ARCHIVE_EXTS)

                if not is_data and not is_archive:
                    continue

                if is_data and self._should_skip(member.name):
                    continue

                f = tar.extractfile(member)
                if not f:
                    continue
                content = f.read()
                out = self._unique_path(dest, basename)
                out.write_bytes(content)

                if is_archive:
                    nested_archives.append(out)
                else:
                    extracted.append(out)

    def _extract_from_zip(self, archive_path: str, dest: str,
                          extracted: list[Path], nested_archives: list[Path]):
        with zipfile.ZipFile(archive_path, "r") as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            ext_counts: dict[str, int] = {}
            for i in infos:
                ext = self._ext_of(i.filename)
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
            logger.info("  Archive contents: %d files %s",
                        len(infos),
                        dict(sorted(ext_counts.items(), key=lambda x: -x[1])))

            for info in infos:
                lower_name = info.filename.lower()
                basename = os.path.basename(info.filename)

                is_data = any(lower_name.endswith(ext) for ext in self._DATA_EXTS)
                is_archive = any(lower_name.endswith(ext) for ext in self._ARCHIVE_EXTS)

                if not is_data and not is_archive:
                    continue

                if is_data and self._should_skip(info.filename):
                    continue

                content = zf.read(info)
                out = self._unique_path(dest, basename)
                out.write_bytes(content)

                if is_archive:
                    nested_archives.append(out)
                else:
                    extracted.append(out)

    def _unique_path(self, dest: str, basename: str) -> Path:
        out = Path(dest) / basename
        counter = 0
        while out.exists():
            counter += 1
            stem = Path(out.stem).stem if out.name.lower().endswith(".json.gz") else out.stem
            out = Path(dest) / f"{stem}_{counter}{self._ext_of(out.name)}"
        return out

    @staticmethod
    def _ext_of(name: str) -> str:
        lower = name.lower()
        for ext in (".tar.gz", ".json.gz"):
            if lower.endswith(ext):
                return ext
        return Path(lower).suffix or "(no ext)"

    @staticmethod
    def _should_skip(name: str) -> bool:
        basename = os.path.basename(name).lower()
        return any(pat in basename for pat in _SKIP_PATTERNS)

    # ---- XML parsing ----

    def _parse_xml(self, path: Path):
        try:
            tree = ET.parse(str(path))
        except ET.ParseError:
            return
        except Exception:
            return

        root = tree.getroot()
        tag = root.tag

        # Detect easyimm XML format: <easyimm><ORG_NAME><pools>...<policies>...<profiles>...<templates>...
        if tag == "easyimm":
            self._parse_easyimm_xml(root)
            return

        if tag == "configResolveClass":
            for child in root.iter():
                if child.tag in _INTERESTING_CLASSES:
                    self._add_mo(child)

        elif tag == "configResolveDn":
            for child in root.iter():
                if child.tag in _INTERESTING_CLASSES:
                    self._add_mo(child)

        elif tag == "configResolveChildren":
            for child in root.iter():
                if child.tag in _INTERESTING_CLASSES:
                    self._add_mo(child)

        elif tag == "configResolveClasses":
            for child in root.iter():
                if child.tag in _INTERESTING_CLASSES:
                    self._add_mo(child)

        elif tag in _INTERESTING_CLASSES:
            self._add_mo(root)
            for child in root.iter():
                if child is not root and child.tag in _INTERESTING_CLASSES:
                    self._add_mo(child)

        else:
            # Try Intersight-style XML with ObjectType attributes
            intersight_found = False
            for child in root.iter():
                obj_type = child.get("ObjectType", "")
                if obj_type and obj_type in _INTERSIGHT_OBJ_TYPES:
                    self._ingest_xml_intersight_mo(child, obj_type)
                    intersight_found = True
                elif child.tag in _INTERESTING_CLASSES:
                    self._add_mo(child)

            if not intersight_found:
                for child in root.iter():
                    if child.tag in _INTERESTING_CLASSES:
                        self._add_mo(child)

            # Try Intersight XML with nested child-text elements
            # (e.g. <mac><name>...</name><mac_blocks><from>...</from></mac_blocks></mac>)
            self._parse_nested_xml_objects(root)

    # Intersight XML nested-element tag → classId mapping
    _NESTED_XML_TAG_MAP: dict[str, str] = {
        "mac": "macpoolPool",
        "uuid": "uuidpoolPool",
        "ip": "ippoolPool",
        "wwpn": "wwpnpoolPool",
        "wwnn": "wwnnpoolPool",
        "iqn": "iqnpoolPool",
        "fc": "fcpoolInitiators",
        # Profiles
        "server_profile": "lsServer",
        "server_profile_template": "lsServer",
        "chassis_profile": "chassisProfile",
        "domain_profile": "fabricClusterProfile",
        "switch_profile": "fabricSwitchProfile",
        # Policies
        "bios_policy": "biosPolicy",
        "boot_policy": "lsbootPolicy",
        "ntp": "commNtpProvider",
        "snmp_policy": "commSnmp",
        "network_control_policy": "nwctrlDefinition",
        "power_policy": "powerPolicy",
        "thermal_policy": "thermalPolicy",
        "kvm_policy": "commKvmMgmtPolicy",
        "vmedia_policy": "cimcvmediaMountConfigPolicy",
        "imc_access_policy": "mgmtAccessPolicy",
        "lan_connectivity_policy": "vnicLanConnPolicy",
        "san_connectivity_policy": "vnicSanConnPolicy",
        "firmware_policy": "firmwareComputeHostPack",
        "eth_network_policy": "fabricEthNetworkPolicy",
        "fc_network_policy": "fabricFcNetworkPolicy",
        "port_policy": "fabricPortPolicy",
        "system_qos_policy": "fabricSystemQosPolicy",
        "switch_control_policy": "fabricSwitchControlPolicy",
        "vlan": "fabricVlan",
        "vsan": "fabricVsan",
    }

    def _parse_nested_xml_objects(self, root, _depth=0):
        """Parse Intersight-style XML with nested child-text elements into MOs."""
        # Log unmapped tags at first level for debugging XML structure
        if _depth < 3 and not self._xml_child_logged.get(f"_nested_{root.tag}"):
            unmapped = [c.tag for c in root if c.tag.lower().strip() not in self._NESTED_XML_TAG_MAP]
            if unmapped:
                logger.info("XML nested unmapped under <%s>: %s", root.tag, unmapped[:15])
                self._xml_child_logged[f"_nested_{root.tag}"] = True

        count = 0
        for element in root:
            tag = element.tag.lower().strip()
            class_id = self._NESTED_XML_TAG_MAP.get(tag)
            if not class_id:
                continue
            obj = self._flatten_xml_element(element)
            obj["_classId"] = class_id
            # Ensure 'name' key exists
            if "name" not in obj and "Name" not in obj:
                obj["name"] = tag
            dn = obj.get("dn", "")
            if dn and dn in self._mos_by_dn:
                continue
            self._mos.setdefault(class_id, []).append(obj)
            if dn:
                self._mos_by_dn[dn] = obj
            moid = obj.get("Moid", obj.get("moid", ""))
            if moid:
                self._mo_by_moid[moid] = obj
            count += 1
        if count:
            logger.info("  Parsed %d nested XML objects", count)

        # Recurse into direct children that aren't mapped themselves
        for element in root:
            tag = element.tag.lower().strip()
            if tag not in self._NESTED_XML_TAG_MAP:
                self._parse_nested_xml_objects(element, _depth + 1)

    def _flatten_xml_element(self, element) -> dict:
        """Flatten an XML element with nested child-text into a flat dict."""
        obj = dict(element.attrib)
        for child in element:
            ctag = child.tag
            if child.text and child.text.strip() and len(child) == 0:
                obj[ctag] = child.text.strip()
            elif len(child) > 0:
                # Nested sub-object (e.g. mac_blocks with from/to/size)
                sub = {}
                for grandchild in child:
                    if grandchild.text and grandchild.text.strip():
                        sub[grandchild.tag] = grandchild.text.strip()
                if sub:
                    key = ctag
                    if key in obj:
                        existing = obj[key]
                        if isinstance(existing, list):
                            existing.append(sub)
                        else:
                            obj[key] = [existing, sub]
                    else:
                        obj[key] = sub
            elif child.attrib:
                obj[ctag] = dict(child.attrib)
        return obj

    # Tag → classId mapping for easyimm policy sections
    _EASYIMM_POLICY_TAG_MAP: dict[str, str] = {
        "bios": "biosPolicy",
        "boot_order": "lsbootPolicy",
        "firmware": "firmwareComputeHostPack",
        "power": "powerPolicy",
        "thermal": "thermalPolicy",
        "virtual_kvm": "commKvmMgmtPolicy",
        "virtual_media": "cimcvmediaMountConfigPolicy",
        "imc_access": "mgmtAccessPolicy",
        "lan_connectivity": "vnicLanConnPolicy",
        "san_connectivity": "vnicSanConnPolicy",
        "ethernet_adapter": "vnicEthAdapterPolicy",
        "ethernet_network_control": "nwctrlDefinition",
        "ethernet_network_group": "vnicEthNetworkGroupPolicy",
        "ethernet_qos": "vnicEthQosPolicy",
        "fibre_channel_adapter": "vnicFcAdapterPolicy",
        "fibre_channel_network": "vnicFcNetworkPolicy",
        "fibre_channel_qos": "vnicFcQosPolicy",
        "ntp": "commNtpProvider",
        "snmp": "commSnmp",
        "multicast": "fabricMulticastPolicy",
        "system_qos": "fabricSystemQosPolicy",
        "switch_control": "fabricSwitchControlPolicy",
        "port": "fabricPortPolicy",
        "network_connectivity": "nwctrlDefinition",
        "local_user": "iamEndPointUserPolicy",
        "storage": "lstorageProfile",
    }

    def _parse_easyimm_xml(self, root):
        """Parse easyimm XML format: <easyimm><ORG><pools>...<policies>...<profiles>...<templates>...</ORG></easyimm>"""
        total = 0
        for org_elem in root:
            org_name = org_elem.tag
            logger.info("Easyimm XML org: %s", org_name)
            for section in org_elem:
                section_tag = section.tag
                if section_tag == "pools":
                    total += self._parse_easyimm_pools(section)
                elif section_tag == "policies":
                    total += self._parse_easyimm_policies(section)
                elif section_tag == "profiles":
                    total += self._parse_easyimm_profiles(section, is_template=False)
                elif section_tag == "templates":
                    total += self._parse_easyimm_profiles(section, is_template=True)
        logger.info("Easyimm XML: parsed %d objects total", total)

    def _parse_easyimm_pools(self, section) -> int:
        """Parse pools section from easyimm XML."""
        count = 0
        for pool_elem in section:
            obj = self._flatten_xml_element(pool_elem)
            tag = pool_elem.tag.lower()
            class_id = self._NESTED_XML_TAG_MAP.get(tag)
            if not class_id:
                continue
            obj["_classId"] = class_id
            if "name" not in obj and "Name" not in obj:
                obj["name"] = tag
            self._mos.setdefault(class_id, []).append(obj)
            count += 1
        if count:
            logger.info("  Easyimm pools: %d objects", count)
        return count

    def _parse_easyimm_policies(self, section) -> int:
        """Parse policies section from easyimm XML."""
        count = 0
        for policy_elem in section:
            tag = policy_elem.tag.lower()
            class_id = self._EASYIMM_POLICY_TAG_MAP.get(tag)
            if not class_id:
                continue
            obj = self._flatten_xml_element(policy_elem)
            obj["_classId"] = class_id
            if "name" not in obj and "Name" not in obj:
                obj["name"] = tag
            self._mos.setdefault(class_id, []).append(obj)
            count += 1
        if count:
            logger.info("  Easyimm policies: %d objects", count)
        return count

    def _parse_easyimm_profiles(self, section, is_template: bool) -> int:
        """Parse profiles/templates section from easyimm XML."""
        count = 0
        label = "templates" if is_template else "profiles"
        for profile_elem in section:
            ptag = profile_elem.tag.lower()
            obj = self._flatten_xml_element(profile_elem)
            name = obj.get("name", "")

            # Extract policy reference names from child tags like <bios_policy>,
            # <lan_connectivity_policy>, etc. (even if values are empty strings)
            policy_refs: dict[str, str] = {}
            for child in profile_elem:
                ctag = child.tag
                text = (child.text or "").strip()
                if ctag.endswith("_policy") or ctag.endswith("_pool"):
                    policy_refs[ctag] = text

            if ptag == "server":
                class_id = "lsServerTemplate" if is_template else "lsServer"
                obj["_classId"] = class_id
                obj["_easyimm_policy_refs"] = policy_refs
                if is_template:
                    obj["type"] = "initial-template"
                    self._easyimm_templates[name] = {
                        "name": name,
                        "policy_refs": policy_refs,
                    }
                else:
                    obj["type"] = "instance"
                    tmpl_ref = obj.get("ucs_server_profile_template", "")
                    self._easyimm_profiles[name] = {
                        "name": name,
                        "template": tmpl_ref,
                        "policy_refs": policy_refs,
                    }
                self._mos.setdefault(class_id, []).append(obj)
                count += 1
            elif ptag == "chassis":
                obj["_classId"] = "chassisProfile"
                self._mos.setdefault("chassisProfile", []).append(obj)
                count += 1
            elif ptag == "domain":
                obj["_classId"] = "fabricClusterProfile"
                self._mos.setdefault("fabricClusterProfile", []).append(obj)
                count += 1
        if count:
            logger.info("  Easyimm %s: %d objects", label, count)
        return count

    def _ingest_xml_intersight_mo(self, element, obj_type: str):
        """Convert an Intersight-style XML element into a JSON-like dict and ingest it."""
        obj = dict(element.attrib)
        obj["ObjectType"] = obj_type
        # Also grab text content from sub-elements as attributes
        for child in element:
            if child.text and child.text.strip():
                obj[child.tag] = child.text.strip()
            elif len(child) == 0 and child.attrib:
                obj[child.tag] = dict(child.attrib)
        self._ingest_json_mo(obj)

    def _add_mo(self, element):
        class_id = element.tag
        attrs = dict(element.attrib)
        attrs["_classId"] = class_id
        dn = attrs.get("dn", "")

        if dn and dn in self._mos_by_dn:
            return

        # Capture child elements as nested MOs (vnicEther/vnicFc inside connectivity policies)
        for child in element:
            child_tag = child.tag
            child_attrs = dict(child.attrib)
            if child_attrs:
                child_attrs["_classId"] = child_tag
                child_attrs["_parentDn"] = dn
                child_dn = child_attrs.get("dn", "")
                if child_dn and child_dn in self._mos_by_dn:
                    continue
                if child_tag in _INTERESTING_CLASSES:
                    self._mos.setdefault(child_tag, []).append(child_attrs)
                    if child_dn:
                        self._mos_by_dn[child_dn] = child_attrs
                elif not self._xml_child_logged.get(class_id):
                    logger.info("XML child of %s: tag=%r attrs=%s", class_id, child_tag,
                                list(child_attrs.keys())[:10])
                    self._xml_child_logged[class_id] = True

        self._mos.setdefault(class_id, []).append(attrs)
        if dn:
            self._mos_by_dn[dn] = attrs

    # ---- JSON parsing (.json.gz / .json) ----

    def _parse_json_file(self, file_path: str):
        """Parse a JSON or gzip-compressed JSON techsupport export."""
        try:
            if file_path.lower().endswith(".gz"):
                with gzip.open(file_path, "rt", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
            else:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Skipping non-JSON file %s: %s", os.path.basename(file_path), e)
            return

        basename = os.path.basename(file_path)
        if isinstance(data, dict):
            top_keys = list(data.keys())[:15]
            logger.info("  JSON top-level keys: %s", top_keys)
            total_keys = len(data)
            for i, key in enumerate(data.keys()):
                if i % max(1, total_keys // 20) == 0:
                    self._emit(f"  Scanning {basename}: key {i+1}/{total_keys}")
                val = data[key]
                if isinstance(val, dict):
                    self._walk_json(val)
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            self._walk_json(item)
        elif isinstance(data, list):
            logger.info("  JSON array with %d items", len(data))
            self._emit(f"  JSON array: {len(data)} items")
            for item in data:
                if isinstance(item, dict):
                    self._walk_json(item)
        mos_so_far = sum(len(v) for v in self._mos.values())
        self._emit(f"  {basename}: done ({mos_so_far} MOs so far)")
        logger.info("  JSON parse of %s complete", basename)

    def _resolve_class_id(self, obj: dict) -> str:
        """Resolve a UCSM-style classId from a JSON MO dict.

        Checks classId/ClassId/_classId first (UCSM format), then falls
        back to ObjectType/object_type (Intersight format) with mapping.
        """
        cid = obj.get("classId") or obj.get("ClassId") or obj.get("_classId") or ""
        if cid and cid in _INTERESTING_CLASSES:
            return cid

        obj_type = obj.get("ObjectType") or obj.get("object_type") or ""
        if obj_type:
            mapped = _INTERSIGHT_OBJ_TYPE_MAP.get(obj_type, "")
            if mapped:
                return mapped

        return cid

    def _walk_json(self, obj: dict, _depth: int = 0, _parent_ctx: dict | None = None):
        """Recursively walk a JSON structure and extract MOs."""
        if _depth > 20:
            return

        class_id = self._resolve_class_id(obj)

        # Build context for child objects
        ctx = dict(_parent_ctx) if _parent_ctx else {}
        if class_id == "networkElement":
            sid = obj.get("SwitchId", obj.get("switchId", ""))
            serial = obj.get("Serial", obj.get("serial", ""))
            if sid:
                ctx["_parent_switchId"] = sid
            if serial:
                ctx["_parent_serial"] = serial
        elif class_id == "equipmentChassis":
            cid = obj.get("ChassisId", obj.get("chassisId", ""))
            if cid:
                ctx["_parent_chassisId"] = str(cid)

        if class_id and class_id in _INTERESTING_CLASSES:
            obj["_classId"] = class_id
            if _parent_ctx:
                obj.setdefault("_parent_ctx", {}).update(_parent_ctx)
            self._ingest_json_mo(obj)

        # Well-known container keys used by UCSM and Intersight JSON formats
        _CONTAINER_KEYS = (
            "outConfigs", "outConfig", "children", "Mos", "mos",
            "Results", "results", "MoList", "moList",
            "Ancestors", "ancestors", "Body", "body",
            "MoConfigs", "ConfigMos", "configMos",
            "Entries", "entries", "Objects", "objects",
            "RegisteredDevices", "HyperflexNodes",
        )
        for key in _CONTAINER_KEYS:
            child_data = obj.get(key)
            if isinstance(child_data, list):
                for item in child_data:
                    if isinstance(item, dict):
                        self._walk_json(item, _depth + 1, ctx)
            elif isinstance(child_data, dict):
                self._walk_json(child_data, _depth + 1, ctx)

        for key, val in obj.items():
            if key.startswith("configResolve") and isinstance(val, dict):
                self._walk_json(val, _depth + 1, ctx)
            elif key in _INTERESTING_CLASSES and isinstance(val, (list, dict)):
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            item.setdefault("_classId", key)
                            if ctx:
                                item.setdefault("_parent_ctx", {}).update(ctx)
                            self._ingest_json_mo(item)
                elif isinstance(val, dict):
                    val.setdefault("_classId", key)
                    if ctx:
                        val.setdefault("_parent_ctx", {}).update(ctx)
                    self._ingest_json_mo(val)

        # Broad recursive scan: walk any dict/list values we haven't
        # already handled if the current object itself wasn't an MO.
        # This catches Intersight domain techsupport keys like
        # "Equipment_Chassis_with_associated_components".
        if not class_id and _depth < 5:
            for key, val in obj.items():
                if key.startswith("_") or key in _CONTAINER_KEYS:
                    continue
                if isinstance(val, dict) and len(val) > 1:
                    self._walk_json(val, _depth + 1, ctx)
                elif isinstance(val, list) and val and isinstance(val[0], dict):
                    for item in val:
                        if isinstance(item, dict):
                            self._walk_json(item, _depth + 1, ctx)
        # Even for MO objects, walk nested lists that contain sub-objects
        # (e.g. equipment.Chassis has Blades, Cards, etc. as nested lists)
        if class_id and _depth < 8:
            for key, val in obj.items():
                if key.startswith("_") or key in _CONTAINER_KEYS:
                    continue
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    for item in val:
                        if isinstance(item, dict) and ("ObjectType" in item or "ClassId" in item or "classId" in item):
                            self._walk_json(item, _depth + 1, ctx)
                elif isinstance(val, dict) and ("ObjectType" in val or "ClassId" in val or "classId" in val):
                    self._walk_json(val, _depth + 1, ctx)

    # Intersight PascalCase → UCSM-style attribute name mapping.
    _INTERSIGHT_FIELD_MAP: dict[str, str] = {
        "Name": "name",
        "Description": "descr",
        "Serial": "serial",
        "Model": "model",
        "Vendor": "vendor",
        "Severity": "severity",
        "Dn": "dn",
        "SwitchId": "switchId",
        "ChassisId": "chassisId",
        "SlotId": "slotId",
        "PortId": "portId",
        "ModuleId": "moduleId",
        "PortChannelId": "portChannelId",
        "OperState": "operState",
        "AdminState": "adminState",
        "OperSpeed": "operSpeed",
        "AdminSpeed": "adminSpeed",
        "Role": "role",
        "Mode": "mode",
        "AllowedVlans": "allowedVlans",
        "NativeVlan": "nativeVlan",
        "AccessVlan": "accessVlan",
        "Version": "version",
        "PackageVersion": "packageVersion",
        "Operability": "operability",
        "Presence": "presence",
        "ConnectionPath": "connPath",
        "ConnectionStatus": "connStatus",
        "OutOfBandIpAddress": "extIp",
        "OutOfBandIpv4Address": "extIp",
        "MgmtIpAddress": "mgmtIpAddress",
        "InbandIpAddress": "ip",
        "OperPowerState": "operPower",
        "NumCpus": "numOfCpus",
        "NumCpuCores": "numOfCores",
        "NumThreads": "numOfThreads",
        "TotalMemory": "totalMemory",
        "AvailableMemory": "availableMemory",
        "BandWidth": "bandwidth",
        "NumPorts": "numPorts",
        "ManagementMode": "mode",
        "NeighborDeviceId": "devId",
        "NeighborPortId": "remotePort",
        "NeighborInterface": "remoteInterface",
        "NeighborModel": "neighborModel",
        "NeighborSerial": "neighborSerial",
        "NeighborVendor": "neighborVendor",
        "NeighborVersion": "neighborVersion",
        "NeighborCapability": "neighborCapability",
        "NeighborNativeVlan": "neighborNativeVlan",
        "NeighborDescription": "neighborDescr",
        "SwitchPortId": "localPort",
        "FaultSummary": "faultSummary",
        "AggregatePortId": "aggrPortId",
        "Type": "type",
        "Component": "component",
        "Capacity": "capacity",
        "PartNumber": "partNumber",
        "FormFactor": "formFactor",
        "MemoryId": "memoryId",
        "ArrayId": "arrayId",
        "DiskId": "diskId",
        "DiskState": "diskState",
        "DriveState": "driveState",
        "Protocol": "protocol",
        "ControllerId": "controllerId",
        "ControllerStatus": "controllerStatus",
        "RaidSupport": "raidSupport",
        "Pid": "pid",
        "Sku": "sku",
        "Revision": "revision",
        "Vid": "vid",
        "PsuId": "psuId",
        "PsuWattage": "psuWattage",
        "PsuType": "psuType",
        "PsuFwVersion": "psuFwVersion",
        "PsuInputSrc": "psuInputSrc",
        "HwRevision": "hwRevision",
        "Cos": "cos",
        "BandwidthPercent": "bandwidthPercent",
        "PacketDrop": "packetDrop",
        "Mtu": "mtu",
        "Weight": "weight",
    }

    def _ingest_json_mo(self, obj: dict):
        """Add a single JSON MO dict to internal storage."""
        # Skip MoRef stubs (just Moid + ObjectType + link, no real data)
        if obj.get("ClassId") == "mo.MoRef" or (len(obj) <= 5 and "link" in obj):
            return

        class_id = obj.get("_classId") or self._resolve_class_id(obj)
        if not class_id or class_id not in _INTERESTING_CLASSES:
            return

        attrs: dict[str, str] = {}
        for k, v in obj.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                attrs[k] = str(v) if v is not None else ""
            # Preserve MoRef dicts needed for cross-object linking
            elif isinstance(v, dict) and k in (
                "AdapterHostEthInterface", "AdapterHostFcInterface",
                "BoundInterface", "PinnedInterface",
                "NetworkElement", "Vethernet",
                "AlarmSummary", "AssignedServer",
                "SrcTemplate",
                # vNIC/vHBA policy references
                "MacPool", "EthAdapterPolicy", "EthQosPolicy",
                "EthNetworkGroupPolicy", "FabricEthNetworkControlPolicy",
                "EthNetworkPolicy",
                "FcAdapterPolicy", "FcQosPolicy", "FcNetworkPolicy",
                "WwpnPool", "WwnnPool", "FcpoolPool",
                # Profile parent reference on vNIC/vHBA definitions
                "Profile", "LanConnectivityPolicy", "SanConnectivityPolicy",
                # Cdn (custom display name)
                "Cdn",
            ):
                attrs[k] = v
            # Preserve list fields needed for profile→policy resolution
            elif isinstance(v, list) and k == "PolicyBucket":
                attrs["_policyBucket"] = v
            elif isinstance(v, list) and k == "AssignedChassis":
                attrs["_AssignedChassis"] = v

        attrs["_classId"] = class_id

        # Map Intersight PascalCase fields to UCSM-style names
        for ifield, ufield in self._INTERSIGHT_FIELD_MAP.items():
            if ifield in attrs and ufield not in attrs:
                attrs[ufield] = attrs[ifield]

        # Inherit parent context (e.g. switchId from FI, chassisId from chassis)
        parent_ctx = obj.get("_parent_ctx", {})
        if parent_ctx:
            if "switchId" not in attrs and "_parent_switchId" in parent_ctx:
                attrs["switchId"] = parent_ctx["_parent_switchId"]
                attrs["_inherited_switchId"] = "true"
            if "chassisId" not in attrs and "_parent_chassisId" in parent_ctx:
                attrs["chassisId"] = parent_ctx["_parent_chassisId"]

        # Synthesize proper UCSM-style DN if missing or in Redfish format
        dn = attrs.get("dn", "")
        if not dn or dn.startswith("/redfish/"):
            dn = self._synthesize_dn(class_id, attrs)
        attrs["dn"] = dn

        # Dedup by Moid first (Intersight primary key), then by DN
        moid = attrs.get("Moid", "")
        dedup_key = moid or dn
        if dedup_key and dedup_key in self._mos_by_dn:
            return

        # For networkElement, use switchId as "id" for the tree builder
        if class_id == "networkElement" and "id" not in attrs:
            attrs["id"] = attrs.get("switchId", "?")
        # For equipmentChassis, use chassisId as "id"
        if class_id == "equipmentChassis" and "id" not in attrs:
            attrs["id"] = attrs.get("chassisId", attrs.get("ChassisId", "?"))
        # For computeBlade, ensure slotId is present
        if class_id == "computeBlade" and "slotId" not in attrs:
            attrs["slotId"] = attrs.get("SlotId", "?")
        # For equipmentIOCard, use moduleId as "id"
        if class_id == "equipmentIOCard" and "id" not in attrs:
            attrs["id"] = attrs.get("moduleId", attrs.get("ModuleId", "?"))
        # For firmwareRunning
        if class_id == "firmwareRunning" and "version" not in attrs:
            attrs["version"] = attrs.get("Version", attrs.get("PackageVersion", ""))
        # For port channels
        if class_id == "fabricEthLanPc":
            if "portId" not in attrs:
                attrs["portId"] = attrs.get("portChannelId", attrs.get("PortChannelId", "?"))
            if "switchId" not in attrs:
                attrs["switchId"] = attrs.get("SwitchId", "?")

        self._mos.setdefault(class_id, []).append(attrs)
        if dedup_key:
            self._mos_by_dn[dedup_key] = attrs

    def _synthesize_dn(self, class_id: str, attrs: dict) -> str:
        """Build a UCSM-style DN from Intersight attributes."""
        moid = attrs.get("Moid", "")

        if class_id == "networkElement":
            sid = attrs.get("switchId", attrs.get("SwitchId", ""))
            serial = attrs.get("serial", attrs.get("Serial", ""))
            if serial:
                return f"sys/switch-{serial}"
            if sid:
                return f"sys/switch-{sid}"
            return moid or "sys/switch-?"

        if class_id == "equipmentChassis":
            cid = attrs.get("chassisId", attrs.get("ChassisId", ""))
            if cid:
                return f"sys/chassis-{cid}"
            return moid or "sys/chassis-?"

        if class_id == "computeBlade":
            cid = attrs.get("chassisId", attrs.get("ChassisId", ""))
            sid = attrs.get("slotId", attrs.get("SlotId", ""))
            if cid and sid:
                return f"sys/chassis-{cid}/blade-{sid}"
            serial = attrs.get("serial", attrs.get("Serial", ""))
            if serial:
                return f"sys/blade-{serial}"
            return moid or "sys/blade-?"

        if class_id == "equipmentIOCard":
            dn = attrs.get("Dn", "")
            if dn:
                return dn
            cid = attrs.get("chassisId", "")
            mid = attrs.get("moduleId", attrs.get("ModuleId", ""))
            if cid and mid:
                return f"sys/chassis-{cid}/slot-{mid}"
            return moid or f"ioc-{moid}"

        if class_id == "firmwareRunning":
            dn = attrs.get("Dn", "")
            if dn:
                return dn
            return moid or "fw-?"

        if class_id == "fabricEthLanPc":
            dn = attrs.get("Dn", "")
            if dn:
                return dn
            return moid or "pc-?"

        if class_id == "networkLanNeighborEntry":
            dn = attrs.get("Dn", "")
            if dn:
                return dn
            return moid or "neighbor-?"

        if class_id == "equipmentSwitchCard":
            dn = attrs.get("Dn", "")
            if dn:
                return dn
            return moid or "slot-?"

        if class_id == "mgmtIf":
            dn = attrs.get("Dn", "")
            if dn:
                return dn
            return moid or "mgmt-?"

        # Generic fallback
        dn = attrs.get("Dn", "")
        return dn or moid or f"{class_id}-{id(attrs)}"

    # ---- Logical tree builder (profiles / policies / pools) ----

    def _build_logical_tree(self) -> dict:
        root = _node(f"Techsupport: {self._filename}", "root")
        root["colours"] = _NODE_COLOURS
        root["categoryColours"] = _CATEGORY_COLOURS
        root["source"] = "techsupport"

        orgs = self._mos.get("orgOrg", [])
        if not orgs:
            orgs = [{"dn": "org-root", "name": "root", "_classId": "orgOrg"}]

        top_orgs = [o for o in orgs if o.get("dn", "").count("/") <= 1]
        if not top_orgs:
            top_orgs = orgs[:1]

        for org in top_orgs:
            org_name = org.get("name", "root")
            org_dn = org.get("dn", "org-root")
            org_node = _node(org_name, "organization",
                             description=org.get("descr", ""))

            # Profiles section (Server, Chassis, Domain)
            profiles_sec = self._build_profiles_section(org_dn)
            if profiles_sec["children"]:
                org_node["children"].append(profiles_sec)

            # Templates section
            templates_sec = self._build_templates_section(org_dn)
            if templates_sec["children"]:
                org_node["children"].append(templates_sec)

            # Policies section (grouped by Intersight UI categories)
            policies = self._build_policies_section(org_dn)
            if policies["children"]:
                org_node["children"].append(policies)

            # Pools
            pools = self._build_pools(org_dn)
            if pools["children"]:
                org_node["children"].append(pools)

            # VLANs / VSANs
            vlans_vsans = self._build_vlans_vsans(org_dn)
            if vlans_vsans["children"]:
                org_node["children"].append(vlans_vsans)

            # Infrastructure (hardware summary)
            infra = self._build_infrastructure()
            if infra["children"]:
                org_node["children"].append(infra)

            # Sub-organizations
            sub_orgs = [o for o in orgs if _dn_parent(o.get("dn", "")) == org_dn and o is not org]
            for sub in sub_orgs:
                sub_node = _node(sub.get("name", "?"), "organization",
                                 description=sub.get("descr", ""))
                sub_dn = sub.get("dn", "")

                sub_profiles = self._build_profiles_section(sub_dn)
                if sub_profiles["children"]:
                    sub_node["children"].append(sub_profiles)
                sub_templates = self._build_templates_section(sub_dn)
                if sub_templates["children"]:
                    sub_node["children"].append(sub_templates)
                sub_policies = self._build_policies_section(sub_dn)
                if sub_policies["children"]:
                    sub_node["children"].append(sub_policies)
                sub_pools = self._build_pools(sub_dn)
                if sub_pools["children"]:
                    sub_node["children"].append(sub_pools)

                if sub_node["children"]:
                    org_node["children"].append(sub_node)

            root["children"].append(org_node)

        return root

    # ---- Infrastructure ----

    def _build_infrastructure(self) -> dict:
        infra = _node("Infrastructure", "group", extra={"colour": "#64748b", "icon": "infra"})

        fis = self._mos.get("networkElement", [])
        if fis:
            for fi in fis:
                fi_id = fi.get("id", fi.get("dn", "?"))
                serial = fi.get("serial", "")
                model = fi.get("model", "")
                label = f"FI-{fi_id}"
                if model:
                    label += f" ({model})"
                desc = f"Serial: {serial}" if serial else ""
                infra["children"].append(_node(label, "fi",
                    description=desc,
                    extra={"colour": "#06b6d4"}))

        chassis_list = self._mos.get("equipmentChassis", [])
        if chassis_list:
            for ch in chassis_list:
                ch_id = ch.get("id", "?")
                ch_name = ch.get("name", "")
                model = ch.get("model", "")
                label = f"Chassis {ch_id}"
                if ch_name:
                    label = f"Chassis {ch_id}: {ch_name}"
                if model:
                    label += f" ({model})"
                blades = [b for b in self._mos.get("computeBlade", [])
                          if (b.get("dn", "").startswith(f"sys/chassis-{ch_id}/")
                              or b.get("chassisId", b.get("ChassisId", "")) == str(ch_id))]
                blade_nodes = []
                for b in blades:
                    slot = b.get("slotId", "?")
                    bname = b.get("name", "")
                    bmodel = b.get("model", "")
                    serial = b.get("serial", "")
                    blabel = f"Blade {slot}"
                    if bname:
                        blabel = f"Blade {slot}: {bname}"
                    if bmodel:
                        blabel += f" ({bmodel})"
                    bdesc = f"Serial: {serial}" if serial else ""
                    blade_nodes.append(_node(blabel, "blade",
                        description=bdesc, extra={"colour": "#34d399"}))

                infra["children"].append(_node(label, "chassis",
                    children=blade_nodes,
                    description=ch.get("serial", ""),
                    extra={"colour": "#f59e0b"}))

        racks = self._mos.get("computeRackUnit", [])
        if racks:
            for r in racks:
                r_id = r.get("serverId", r.get("id", "?"))
                model = r.get("model", "")
                serial = r.get("serial", "")
                label = f"Rack Server {r_id}"
                if model:
                    label += f" ({model})"
                desc = f"Serial: {serial}" if serial else ""
                infra["children"].append(_node(label, "rack_server",
                    description=desc, extra={"colour": "#34d399"}))

        return infra

    # ---- VLANs / VSANs ----

    def _build_vlans_vsans(self, org_dn: str) -> dict:
        group = _node("VLANs / VSANs", "group", extra={"colour": "#3b82f6"})

        vlans = self._mos.get("fabricVlan", [])
        if vlans:
            vlan_group = _node(f"VLANs ({len(vlans)})", "group", extra={"colour": "#3b82f6"})
            for v in sorted(vlans, key=lambda x: int(x.get("id", "0") or "0")):
                vid = v.get("id", "?")
                name = v.get("name", "")
                label = f"VLAN {vid}"
                if name:
                    label += f": {name}"
                vlan_group["children"].append(_node(label, "vlan",
                    extra={"colour": "#3b82f6"}))
            group["children"].append(vlan_group)

        vsans = self._mos.get("fabricVsan", [])
        if vsans:
            vsan_group = _node(f"VSANs ({len(vsans)})", "group", extra={"colour": "#8b5cf6"})
            for v in sorted(vsans, key=lambda x: int(x.get("id", "0") or "0")):
                vid = v.get("id", "?")
                name = v.get("name", "")
                label = f"VSAN {vid}"
                if name:
                    label += f": {name}"
                vsan_group["children"].append(_node(label, "vsan",
                    extra={"colour": "#8b5cf6"}))
            group["children"].append(vsan_group)

        return group

    # ---- Profiles Section (Server / Chassis / Domain) ----

    def _build_profiles_section(self, org_dn: str) -> dict:
        """Build Profiles group with Server, Chassis, and Domain sub-groups."""
        group = _node("Profiles", "group",
                       extra={"colour": "#10b981", "icon": "profiles"})

        # Server profiles (instances only)
        all_server = self._mos.get("lsServer", [])
        server_instances = [
            p for p in all_server
            if p.get("type", "") != "initial-template"
            and p.get("type", "") != "updating-template"
            and "template" not in p.get("type", "").lower()
        ]
        # If no 'type' field (Intersight), treat all lsServer as profiles
        if not server_instances:
            server_instances = all_server

        # Deduplicate by name (prefer MOs with Moid over easyimm ones)
        seen_prof_names: set[str] = set()
        deduped: list[dict] = []
        for p in sorted(server_instances, key=lambda x: (0 if x.get("Moid") else 1, x.get("name", ""))):
            pname = p.get("name", p.get("Name", ""))
            if pname and pname in seen_prof_names:
                continue
            if pname:
                seen_prof_names.add(pname)
            deduped.append(p)
        server_instances = deduped

        if server_instances:
            sp_group = _node(f"Server Profiles ({len(server_instances)})", "group",
                             extra={"colour": "#34d399"})
            for p in sorted(server_instances, key=lambda x: x.get("name", "")):
                sp_group["children"].append(
                    self._build_profile_node(p, is_template=False, profile_type="server"))
            group["children"].append(sp_group)

        # Chassis profiles
        chassis_profs = self._mos.get("chassisProfile", [])
        if chassis_profs:
            cp_group = _node(f"Chassis Profiles ({len(chassis_profs)})", "group",
                             extra={"colour": "#f59e0b"})
            for p in sorted(chassis_profs, key=lambda x: x.get("name", "")):
                cp_group["children"].append(
                    self._build_profile_node(p, is_template=False, profile_type="chassis"))
            group["children"].append(cp_group)

        # Domain profiles (SwitchClusterProfile)
        domain_profs = self._mos.get("fabricClusterProfile", [])
        if domain_profs:
            dp_group = _node(f"Domain Profiles ({len(domain_profs)})", "group",
                             extra={"colour": "#8b5cf6"})
            for p in sorted(domain_profs, key=lambda x: x.get("name", "")):
                dp_group["children"].append(
                    self._build_profile_node(p, is_template=False, profile_type="domain"))
            group["children"].append(dp_group)

        # Switch profiles
        switch_profs = self._mos.get("fabricSwitchProfile", [])
        if switch_profs:
            sw_group = _node(f"Switch Profiles ({len(switch_profs)})", "group",
                             extra={"colour": "#06b6d4"})
            for p in sorted(switch_profs, key=lambda x: x.get("name", "")):
                sw_group["children"].append(
                    self._build_profile_node(p, is_template=False, profile_type="switch"))
            group["children"].append(sw_group)

        return group

    # ---- Templates Section ----

    def _build_templates_section(self, org_dn: str) -> dict:
        """Build Templates group with Server, Chassis sub-groups."""
        group = _node("Templates", "group",
                       extra={"colour": "#8b5cf6", "icon": "template"})

        # Server profile templates from multiple sources
        all_server = self._mos.get("lsServer", [])
        templates = [p for p in all_server
                     if "template" in p.get("type", "").lower()]
        # Explicit server.ProfileTemplate MOs
        templates += self._mos.get("lsServerTemplate", [])

        # Also discover templates referenced by SrcTemplate but not in data
        # (creates placeholder entries so we at least show the name)
        seen_names: set[str] = set()
        for t in templates:
            tname = t.get("name", t.get("Name", ""))
            if tname:
                seen_names.add(tname)
        if hasattr(self, "_mo_by_moid"):
            for p in all_server:
                src = p.get("SrcTemplate")
                if isinstance(src, dict):
                    tmoid = src.get("Moid", "")
                    tmo = self._mo_by_moid.get(tmoid, {})
                    tname = tmo.get("name", tmo.get("Name", ""))
                    if tname and tname not in seen_names:
                        seen_names.add(tname)
                        templates.append(tmo if tmo else {"name": tname, "Moid": tmoid})
                elif p.get("srcTemplName"):
                    stname = p["srcTemplName"]
                    if stname not in seen_names:
                        seen_names.add(stname)
                        templates.append({"name": stname, "type": "template"})

        # Deduplicate
        seen_final: set[str] = set()
        unique_templates = []
        for t in templates:
            tname = t.get("name", t.get("Name", ""))
            if tname and tname not in seen_final:
                seen_final.add(tname)
                unique_templates.append(t)

        logger.info("Templates section: found %d server templates", len(unique_templates))

        if unique_templates:
            st_group = _node(f"Server Templates ({len(unique_templates)})", "group",
                             extra={"colour": "#10b981"})
            for t in sorted(unique_templates, key=lambda x: x.get("name", "")):
                t_node = self._build_profile_node(t, is_template=True, profile_type="server")
                t_moid = t.get("Moid", "")
                t_name = t.get("name", t.get("Name", ""))
                # Show derived profiles (UCSM: by srcTemplName, Intersight: by SrcTemplate Moid)
                derived = []
                for p in all_server:
                    if p.get("srcTemplName", "") == t_name and p.get("type", "") == "instance":
                        derived.append(p)
                    elif isinstance(p.get("SrcTemplate"), dict):
                        if p["SrcTemplate"].get("Moid", "") == t_moid and t_moid:
                            derived.append(p)
                if derived:
                    derived_group = _node(f"Derived Profiles ({len(derived)})", "group",
                                          extra={"colour": "#34d399"})
                    for d in sorted(derived, key=lambda x: x.get("name", "")):
                        d_node = self._build_profile_node(d, is_template=False, profile_type="server")
                        derived_group["children"].append(d_node)
                    t_node["children"].insert(0, derived_group)
                st_group["children"].append(t_node)
            group["children"].append(st_group)

        # Chassis profile templates
        ch_templates = self._mos.get("chassisProfileTemplate", [])
        if ch_templates:
            ct_group = _node(f"Chassis Templates ({len(ch_templates)})", "group",
                             extra={"colour": "#f59e0b"})
            for t in sorted(ch_templates, key=lambda x: x.get("name", "")):
                ct_group["children"].append(
                    self._build_profile_node(t, is_template=True, profile_type="chassis"))
            group["children"].append(ct_group)

        # vNIC / vHBA templates
        vnic_tmpls = self._mos.get("vnicLanConnTempl", [])
        vhba_tmpls = self._mos.get("vnicSanConnTempl", [])
        if vnic_tmpls:
            vn_group = _node(f"vNIC Templates ({len(vnic_tmpls)})", "group",
                             extra={"colour": "#ec4899"})
            for v in sorted(vnic_tmpls, key=lambda x: x.get("name", "")):
                vn_group["children"].append(_node(
                    v.get("name", "?"), "vnic",
                    description=v.get("descr", ""),
                    extra={"colour": "#ec4899"},
                ))
            group["children"].append(vn_group)
        if vhba_tmpls:
            vh_group = _node(f"vHBA Templates ({len(vhba_tmpls)})", "group",
                             extra={"colour": "#f43f5e"})
            for v in sorted(vhba_tmpls, key=lambda x: x.get("name", "")):
                vh_group["children"].append(_node(
                    v.get("name", "?"), "vhba",
                    description=v.get("descr", ""),
                    extra={"colour": "#f43f5e"},
                ))
            group["children"].append(vh_group)

        return group

    # ---- Single profile/template node ----

    def _build_profile_node(self, profile: dict, *, is_template: bool,
                            profile_type: str = "server") -> dict:
        ntype_map = {
            ("server", True): "server_profile_template",
            ("server", False): "server_profile",
            ("chassis", True): "chassis_profile",
            ("chassis", False): "chassis_profile",
            ("domain", True): "domain_profile",
            ("domain", False): "domain_profile",
            ("switch", True): "switch_profile",
            ("switch", False): "switch_profile",
        }
        ntype = ntype_map.get((profile_type, is_template), "server_profile")
        name = profile.get("name", "?")
        dn = profile.get("dn", "")
        pn_server = profile.get("pnDn", "")

        # Resolve source template name
        tmpl_name = ""
        src_templ = profile.get("SrcTemplate")
        if isinstance(src_templ, dict):
            tmpl_moid = src_templ.get("Moid", "")
            if tmpl_moid and hasattr(self, "_mo_by_moid"):
                tmpl_mo = self._mo_by_moid.get(tmpl_moid, {})
                tmpl_name = tmpl_mo.get("name", tmpl_mo.get("Name", ""))
            if not tmpl_name:
                for pinfo in self._server_profile_info.values():
                    if pinfo.get("name") == name and pinfo.get("template"):
                        tmpl_name = pinfo["template"]
                        break
            if not tmpl_name and tmpl_moid:
                tmpl_name = f"(Moid: {tmpl_moid[:12]}…)"
        elif profile.get("srcTemplName"):
            tmpl_name = profile["srcTemplName"]

        # Build structured description — structured fields first, notes last
        desc_parts = []
        ptype_label = profile_type.replace("_", " ").title()
        desc_parts.append(f"Type: {ptype_label} {'Template' if is_template else 'Profile'}")
        if tmpl_name:
            desc_parts.append(f"Derived from Template: {tmpl_name}")
        # Assigned server
        if pn_server:
            desc_parts.append(f"Assigned Server: {pn_server}")
        assigned_ref = profile.get("AssignedServer")
        if isinstance(assigned_ref, dict):
            srv_moid = assigned_ref.get("Moid", "")
            if srv_moid and hasattr(self, "_mo_by_moid"):
                srv_mo = self._mo_by_moid.get(srv_moid, {})
                srv_name = srv_mo.get("name", srv_mo.get("Name", ""))
                srv_serial = _mo_serial(srv_mo)
                if srv_name or srv_serial:
                    desc_parts.append(f"Assigned Server: {srv_name or ''} (SN: {srv_serial})" if srv_serial else f"Assigned Server: {srv_name}")
        # Deploy status
        deploy_status = profile.get("ConfigState", profile.get("configState", ""))
        if deploy_status:
            desc_parts.append(f"Deploy Status: {deploy_status}")
        # User notes (freeform description) — at the bottom
        descr = profile.get("descr", profile.get("Description", ""))
        if descr:
            desc_parts.append(f"Notes: {descr}")

        extra = {}
        if pn_server:
            extra["assignedServer"] = pn_server

        node = _node(name, ntype,
                     description="\n".join(desc_parts),
                     extra=extra or None)

        # Source template reference — show as a visible child node
        if tmpl_name and not is_template:
            node["children"].append(_node(
                f"Template: {tmpl_name}", "server_profile_template",
                extra={"colour": "#8b5cf6"},
            ))

        # Try PolicyBucket-based resolution first (Intersight profiles)
        bucket = profile.get("_policyBucket", [])
        if bucket:
            prof_name = profile.get("name", "")
            policies = self._profile_name_policy_map.get(prof_name, [])
            pol_node = self._build_policy_nodes(policies)
            if pol_node:
                node["children"].append(pol_node)
            # Resolve pool references from policies
            pool_children = self._resolve_profile_pools(policies)
            if pool_children:
                pool_group = _node("Pools", "group", extra={"colour": "#06b6d4"})
                pool_group["children"] = pool_children
                node["children"].append(pool_group)
        else:
            # Fall back to UCSM name-reference attributes
            policy_children = self._resolve_profile_policies(profile)
            if policy_children:
                node["children"].extend(policy_children)

        # vNICs
        vnics = [m for m in self._mos.get("vnicEther", [])
                 if m.get("dn", "").startswith(dn + "/")]
        if vnics:
            for v in sorted(vnics, key=lambda x: _safe_int(x.get("order", "0"))):
                vname = v.get("name", "vNIC")
                switch_id = v.get("switchId", "")
                label = f"vNIC: {vname}"
                if switch_id:
                    label += f" (Fabric {switch_id})"
                sub = []
                for attr, plabel in [
                    ("adaptorProfileName", "Adapter Policy"),
                    ("nwCtrlPolicyName", "Network Control"),
                    ("qosPolicyName", "QoS Policy"),
                    ("nwTemplName", "vNIC Template"),
                    ("identPoolName", "MAC Pool"),
                ]:
                    val = v.get(attr, "")
                    if val:
                        sub.append(_node(f"{plabel}: {val}", "policy",
                                         extra={"colour": "#ec4899"}))
                node["children"].append(_node(label, "vnic", children=sub))

        # vHBAs
        vhbas = [m for m in self._mos.get("vnicFc", [])
                 if m.get("dn", "").startswith(dn + "/")]
        if vhbas:
            for v in sorted(vhbas, key=lambda x: _safe_int(x.get("order", "0"))):
                vname = v.get("name", "vHBA")
                switch_id = v.get("switchId", "")
                label = f"vHBA: {vname}"
                if switch_id:
                    label += f" (Fabric {switch_id})"
                sub = []
                for attr, plabel in [
                    ("adaptorProfileName", "FC Adapter Policy"),
                    ("qosPolicyName", "FC QoS Policy"),
                    ("nwTemplName", "vHBA Template"),
                    ("identPoolName", "WWPN Pool"),
                ]:
                    val = v.get(attr, "")
                    if val:
                        sub.append(_node(f"{plabel}: {val}", "policy",
                                         extra={"colour": "#f43f5e"}))
                node["children"].append(_node(label, "vhba", children=sub))

        return node

    def _resolve_profile_policies(self, profile: dict) -> list[dict]:
        """Turn name-reference attributes into categorized policy nodes (UCSM style)."""
        by_cat: dict[str, list[dict]] = {}

        for attr, (class_id, display) in _PROFILE_POLICY_ATTRS.items():
            val = profile.get(attr, "")
            if not val:
                continue
            cat = _CLASS_TO_CAT.get(class_id, "Other")
            colour = _CATEGORY_COLOURS.get(cat, "#94a3b8")
            pnode = _node(f"{display}: {val}", "policy", extra={"colour": colour, "category": cat})
            by_cat.setdefault(cat, []).append(pnode)

        result = []
        for cat in ["Compute", "Management", "Networking", "Storage",
                     "Infrastructure", "Power & Thermal", "Monitoring", "Other"]:
            policies = by_cat.get(cat)
            if not policies:
                continue
            result.append(_node(cat, "policy_category",
                                children=policies,
                                extra={"colour": _CATEGORY_COLOURS.get(cat, "#94a3b8")}))
        return result

    # ---- Policies Section (all categories) ----

    def _build_policies_section(self, org_dn: str) -> dict:
        """Build policies grouped by Intersight UI categories."""
        group = _node("Policies", "group", extra={"colour": "#64748b"})

        cat_order = [
            "Compute", "Management", "Networking", "Storage",
            "Infrastructure", "Power & Thermal", "Monitoring",
        ]

        for cat in cat_order:
            class_ids = _POLICY_CATEGORIES.get(cat, [])
            cat_children: list[dict] = []

            for cid in class_ids:
                mos = self._mos.get(cid, [])
                for mo in mos:
                    name = mo.get("name", mo.get("Name", mo.get("dn", "?")))
                    display = _POLICY_DISPLAY.get(cid, cid)
                    desc_parts = []
                    descr = mo.get("descr", mo.get("Description", ""))
                    if descr:
                        desc_parts.append(f"Description: {descr}")
                    # Collect non-trivial attributes for the description
                    skip = {"_classId", "dn", "Moid", "name", "Name",
                            "ObjectType", "ClassId", "descr", "Description",
                            "_policyBucket", "_AssignedChassis",
                            "AssignedServer", "SrcTemplate",
                            "AccountMoid", "DomainGroupMoid",
                            "SharedScope", "CreateTime", "ModTime",
                            "Ancestors", "PermissionResources", "Tags",
                            "VersionContext", "Organization",
                            "_parent_ctx", "_inherited_switchId"}
                    for pk, pv in mo.items():
                        if pk in skip or pk.startswith("_"):
                            continue
                        if isinstance(pv, (str, int, float, bool)) and str(pv):
                            desc_parts.append(f"{pk}: {pv}")
                    cat_children.append(_node(
                        f"{display}: {name}", "policy",
                        description="\n".join(desc_parts[:40]),
                        extra={
                            "colour": _CATEGORY_COLOURS.get(cat, "#94a3b8"),
                            "moid": mo.get("Moid", ""),
                        },
                    ))

            if cat_children:
                group["children"].append(_node(
                    f"{cat} ({len(cat_children)})", "policy_category",
                    children=cat_children,
                    extra={"colour": _CATEGORY_COLOURS.get(cat, "#94a3b8")}))

        return group

    # ---- Pools ----

    def _build_pools(self, org_dn: str) -> dict:
        group = _node("Pools", "group", extra={"colour": "#06b6d4"})

        pool_classes = [
            ("macpoolPool", "MAC Pool"),
            ("uuidpoolPool", "UUID Pool"),
            ("fcpoolInitiators", "FC Pool"),
            ("ippoolPool", "IP Pool"),
            ("iqnpoolPool", "IQN Pool"),
            ("resourcepoolPool", "Resource Pool"),
            ("wwpnpoolPool", "WWPN Pool"),
            ("wwnnpoolPool", "WWNN Pool"),
        ]

        for cid, display in pool_classes:
            mos = self._mos.get(cid, [])
            if mos:
                logger.info("  Pools section: %s → %d MOs", cid, len(mos))
            for mo in mos:
                name = mo.get("name", mo.get("Name", "?"))
                size = mo.get("size", mo.get("Size", ""))
                assigned = mo.get("assigned", mo.get("Assigned", ""))
                assignment_order = mo.get("assignment_order", mo.get("AssignmentOrder", ""))
                desc_parts = []
                if size:
                    desc_parts.append(f"Size: {size}")
                if assigned:
                    desc_parts.append(f"Assigned: {assigned}")
                if assignment_order:
                    desc_parts.append(f"Assignment Order: {assignment_order}")
                # Block ranges from nested XML (mac_blocks, ip_blocks, etc.)
                for bkey in ("mac_blocks", "ip_blocks", "uuid_blocks",
                             "wwpn_blocks", "wwnn_blocks", "iqn_blocks",
                             "fc_blocks", "IpV4Blocks", "IpV6Blocks"):
                    block = mo.get(bkey)
                    if isinstance(block, dict):
                        bfrom = block.get("from", block.get("From", ""))
                        bto = block.get("to", block.get("To", ""))
                        bsize = block.get("size", block.get("Size", ""))
                        if bfrom and bto:
                            desc_parts.append(f"Range: {bfrom} → {bto}")
                        if bsize and not size:
                            desc_parts.append(f"Size: {bsize}")
                    elif isinstance(block, list):
                        for bi, b in enumerate(block):
                            bfrom = b.get("from", b.get("From", ""))
                            bto = b.get("to", b.get("To", ""))
                            if bfrom and bto:
                                desc_parts.append(f"Range {bi+1}: {bfrom} → {bto}")
                descr = mo.get("descr", mo.get("Description", ""))
                if descr:
                    desc_parts.append(f"Description: {descr}")
                group["children"].append(_node(
                    f"{display}: {name}", "pool",
                    description="\n".join(desc_parts),
                    extra={"colour": "#06b6d4"},
                ))

        # If no pool MOs exist, synthesize from vNIC/vHBA/profile references
        if not group["children"]:
            seen_pools: dict[str, set[str]] = {}
            vnics = self._mos.get("vnicEther", [])
            logger.info("  Pool synthesis: %d vnicEther MOs to scan", len(vnics))
            if vnics:
                sample = vnics[0]
                logger.info("  vnicEther sample keys: %s", list(sample.keys())[:20])
            # MAC pools from vNICs
            for v in vnics:
                pname = v.get("identPoolName", "")
                if pname:
                    seen_pools.setdefault("MAC Pool", set()).add(pname)
            # WWPN/WWNN pools from vHBAs
            for v in self._mos.get("vnicFc", []):
                pname = v.get("identPoolName", "")
                if pname:
                    seen_pools.setdefault("WWPN Pool", set()).add(pname)
            # UUID pools from server profiles
            for sp in self._mos.get("lsServer", []):
                uuid_pool = sp.get("uuidPoolName", sp.get("identPoolName", ""))
                if uuid_pool:
                    seen_pools.setdefault("UUID Pool", set()).add(uuid_pool)
                # Server pool
                spool = sp.get("srcTemplName", "")
                mgmt_pool = sp.get("mgmtAccessPolicyName", "")
                if mgmt_pool:
                    pass
            # IP pool from management interfaces
            for m in self._mos.get("mgmtIf", []):
                ip_pool = m.get("poolName", m.get("extPoolName", ""))
                if ip_pool:
                    seen_pools.setdefault("IP Pool", set()).add(ip_pool)

            for pool_type, names in sorted(seen_pools.items()):
                for name in sorted(names):
                    group["children"].append(_node(
                        f"{pool_type}: {name}", "pool",
                        description="Discovered from profile/vNIC/vHBA references",
                        extra={"colour": "#06b6d4"},
                    ))

        return group

    # ====================================================================
    # Policy node builder (shared by physical view builders)
    # ====================================================================

    def _build_policy_nodes(self, policies: list[dict]) -> dict | None:
        """Build a 'Policies' group node from a list of resolved policy dicts."""
        if not policies:
            return None
        by_category: dict[str, list[dict]] = defaultdict(list)
        for p in policies:
            by_category[p["category"]].append(p)

        cat_order = [
            "Compute", "Management", "Networking", "Storage",
            "Infrastructure", "Power & Thermal", "Monitoring", "Other",
        ]
        policy_children = []
        for cat_name in cat_order:
            items = by_category.get(cat_name)
            if not items:
                continue
            cat_items = []
            for p in items:
                cat_items.append(_node(
                    f"{p['type']}: {p['name']}", "policy",
                    description=p.get("description", ""),
                    extra={
                        "colour": p.get("colour", "#94a3b8"),
                        "moid": p.get("moid", ""),
                    },
                ))
            policy_children.append(_node(
                f"{cat_name} ({len(cat_items)})", "policy_category",
                children=cat_items,
                extra={"colour": _CATEGORY_COLOURS.get(cat_name, "#94a3b8")},
            ))
        # Handle any remaining categories not in the predefined order
        for cat_name in sorted(by_category):
            if cat_name in cat_order:
                continue
            items = by_category[cat_name]
            cat_items = []
            for p in items:
                cat_items.append(_node(
                    f"{p['type']}: {p['name']}", "policy",
                    description=p.get("description", ""),
                    extra={
                        "colour": p.get("colour", "#94a3b8"),
                        "moid": p.get("moid", ""),
                    },
                ))
            policy_children.append(_node(
                f"{cat_name} ({len(cat_items)})", "policy_category",
                children=cat_items,
                extra={"colour": _CATEGORY_COLOURS.get(cat_name, "#94a3b8")},
            ))

        return _node(
            f"Policies ({len(policies)})", "group",
            children=policy_children,
            extra={"colour": "#8b5cf6"},
        )

    def _resolve_profile_pools(self, policies: list[dict]) -> list[dict]:
        """Extract pool references from a profile's resolved policies."""
        pool_nodes = []
        seen = set()
        pool_classes = {
            "macpoolPool": "MAC Pool",
            "uuidpoolPool": "UUID Pool",
            "fcpoolInitiators": "WWPN Pool",
            "ippoolPool": "IP Pool",
            "iqnpoolPool": "IQN Pool",
            "resourcepoolPool": "Resource Pool",
            "wwpnpoolPool": "WWPN Pool",
            "wwnnpoolPool": "WWNN Pool",
        }
        for p in policies:
            moid = p.get("moid", "")
            if not moid:
                continue
            pol_mo = self._mo_by_moid.get(moid, {})
            for attr in ("MacPool", "WwpnPool", "WwnnPool", "FcpoolPool",
                         "IpPool", "UuidPool", "IqnPool"):
                ref = pol_mo.get(attr)
                if isinstance(ref, dict):
                    pool_moid = ref.get("Moid", "")
                    if pool_moid and pool_moid not in seen:
                        seen.add(pool_moid)
                        pool_mo = self._mo_by_moid.get(pool_moid, {})
                        pool_name = pool_mo.get("name", pool_mo.get("Name", f"Moid:{pool_moid[:12]}"))
                        pool_type = attr.replace("Pool", " Pool").replace("Fcpool ", "FC ")
                        pool_nodes.append(_node(
                            f"{pool_type}: {pool_name}", "pool",
                            extra={"colour": "#06b6d4"},
                        ))
        # Also look at standalone pool MOs matching by name references
        for cid, display in pool_classes.items():
            for mo in self._mos.get(cid, []):
                mo_moid = mo.get("Moid", mo.get("moid", ""))
                if mo_moid and mo_moid not in seen:
                    name = mo.get("name", mo.get("Name", ""))
                    for p in policies:
                        p_moid = p.get("moid", "")
                        p_mo = self._mo_by_moid.get(p_moid, {})
                        for attr_val in p_mo.values():
                            if isinstance(attr_val, dict) and attr_val.get("Moid") == mo_moid:
                                seen.add(mo_moid)
                                pool_nodes.append(_node(
                                    f"{display}: {name}", "pool",
                                    extra={"colour": "#06b6d4"},
                                ))
                                break
        return pool_nodes

    # ====================================================================
    # Physical tree builder
    # ====================================================================

    def _build_physical_tree(self) -> dict:
        root = _node(f"Physical: {self._filename}", "root")
        root["colours"] = _NODE_COLOURS
        root["categoryColours"] = _CATEGORY_COLOURS
        root["source"] = "techsupport"
        root["view"] = "physical"

        disjoint_vlans = self._detect_disjoint_vlans()

        fi_section = self._build_fi_section(disjoint_vlans)
        if fi_section["children"]:
            root["children"].append(fi_section)

        if disjoint_vlans:
            summary = _node(
                f"Disjoint VLAN Summary ({len(disjoint_vlans)})", "group",
                extra={"colour": "#dc2626", "disjoint": True},
            )
            for vid in sorted(disjoint_vlans, key=lambda v: int(v) if v.isdigit() else 0):
                info = disjoint_vlans[vid]
                fabric = info["fabric"]
                ports_str = ", ".join(info["ports"][:8])
                if len(info["ports"]) > 8:
                    ports_str += f" (+{len(info['ports']) - 8} more)"
                label = f"VLAN {vid}: {info.get('name', '')} — {fabric} only"
                desc = f"Interfaces: {ports_str}" if ports_str else ""
                summary["children"].append(_node(
                    label, "disjoint_vlan",
                    description=desc,
                    extra={"colour": "#dc2626", "disjoint": True},
                ))
            root["children"].append(summary)

        chassis_sec = self._build_chassis_physical()
        if chassis_sec["children"]:
            root["children"].append(chassis_sec)

        rack_sec = self._build_racks_physical()
        if rack_sec["children"]:
            root["children"].append(rack_sec)

        vlans_sec = self._build_vlans_physical(disjoint_vlans)
        if vlans_sec["children"]:
            root["children"].append(vlans_sec)

        vsans_sec = self._build_vsans_physical()
        if vsans_sec["children"]:
            root["children"].append(vsans_sec)

        return root

    # ---- Disjoint VLAN detection ----

    def _detect_disjoint_vlans(self) -> dict[str, dict]:
        """Return dict of VLAN IDs that exist on one fabric but not the other.

        Returns ``{vlan_id: {"name": ..., "fabric": "FI-A only"|"FI-B only", "ports": [...]}}``.
        """
        vlans = self._mos.get("fabricVlan", [])
        a_vlans: dict[str, str] = {}
        b_vlans: dict[str, str] = {}

        for v in vlans:
            vid = v.get("id", "")
            name = v.get("name", "")
            sid = v.get("switchId", "dual").upper()
            if not vid:
                continue
            if sid == "A":
                a_vlans[vid] = name
            elif sid == "B":
                b_vlans[vid] = name
            # "dual" or "DUAL" means on both — not disjoint

        disjoint: dict[str, dict] = {}
        for vid, name in a_vlans.items():
            if vid not in b_vlans:
                disjoint[vid] = {"name": name, "fabric": "FI-A only", "ports": []}
        for vid, name in b_vlans.items():
            if vid not in a_vlans:
                disjoint[vid] = {"name": name, "fabric": "FI-B only", "ports": []}

        vlan_port_eps = self._mos.get("fabricEthVlanPortEp", [])
        for ep in vlan_port_eps:
            ep_dn = ep.get("dn", "")
            ep_vlan = ep.get("vlanId", "") or self._vlan_id_from_dn(ep_dn)
            if ep_vlan in disjoint:
                port_label = f"Eth{ep.get('slotId', '?')}/{ep.get('portId', '?')}"
                disjoint[ep_vlan]["ports"].append(port_label)

        return disjoint

    @staticmethod
    def _vlan_id_from_dn(dn: str) -> str:
        """Try to extract a VLAN ID from a fabricEthVlanPortEp DN."""
        for part in dn.split("/"):
            if part.startswith("net-"):
                return part.replace("net-", "")
        return ""

    # ---- FI section with ports ----

    def _build_fi_section(self, disjoint_vlans: dict) -> dict:
        section = _node("Fabric Interconnects", "group", extra={"colour": "#06b6d4"})

        fis = self._mos.get("networkElement", [])
        for fi in sorted(fis, key=lambda f: f.get("id", f.get("switchId", ""))):
            section["children"].append(self._build_fi_detailed(fi, disjoint_vlans))

        return section

    def _build_fi_detailed(self, fi: dict, disjoint_vlans: dict) -> dict:
        fi_id = fi.get("id", fi.get("switchId", "?"))
        serial = _mo_serial(fi)
        model = fi.get("model", "")
        fi_dn = fi.get("dn", "")

        fw = self._find_firmware(fi_dn, serial)
        mgmt_ip = self._find_mgmt_ip(fi_id, fi)

        label = f"FI-{fi_id}"
        if model:
            label += f" ({model})"

        desc_parts = _mo_ident_parts(fi)
        if fw:
            desc_parts.append(f"FW: {fw}")
        if mgmt_ip:
            desc_parts.append(f"Mgmt: {mgmt_ip}")

        fi_node = _node(label, "fi",
                        description="\n".join(desc_parts),
                        extra={"colour": "#06b6d4"})

        uplinks = self._build_port_group(
            "Uplink Ports", "fabricEthLanEp", fi_id, "uplink_port", disjoint_vlans,
        )
        if uplinks["children"]:
            fi_node["children"].append(uplinks)

        server_ports = self._build_port_group(
            "Server Ports", "fabricDceSwSrvEp", fi_id, "server_port", disjoint_vlans,
        )
        if server_ports["children"]:
            fi_node["children"].append(server_ports)

        fc_ports = self._build_fc_port_group(fi_id)
        if fc_ports["children"]:
            fi_node["children"].append(fc_ports)

        pcs = self._build_port_channels(fi_id)
        if pcs["children"]:
            fi_node["children"].append(pcs)

        neighbors = self._build_neighbor_section(fi_id)
        if neighbors["children"]:
            fi_node["children"].append(neighbors)

        qos_section = self._build_qos_section()
        if qos_section["children"]:
            fi_node["children"].append(qos_section)

        # FI firmware
        fi_fw_items = []
        for fw_mo in self._mos.get("firmwareRunning", []):
            fw_dn = fw_mo.get("dn", "")
            if not ((fi_dn and fw_dn.startswith(fi_dn)) or (serial and serial in fw_dn and "switch-" in fw_dn)):
                continue
            fw_ver = fw_mo.get("version", fw_mo.get("Version", ""))
            fw_comp = fw_mo.get("component", fw_mo.get("Component", ""))
            fw_type = fw_mo.get("type", fw_mo.get("Type", ""))
            if not fw_ver:
                continue
            pkg_ver = fw_mo.get("packageVersion", fw_mo.get("PackageVersion", ""))
            fw_desc = []
            if fw_type:
                fw_desc.append(f"Type: {fw_type}")
            if fw_comp:
                fw_desc.append(f"Component: {fw_comp}")
            fw_desc.append(f"Version: {fw_ver}")
            if pkg_ver and pkg_ver != fw_ver:
                fw_desc.append(f"Package: {pkg_ver}")
            fi_fw_items.append(_node(
                f"{'NX-OS' if fw_type == 'switch-software' else fw_type or 'FW'}: {fw_ver}",
                "firmware",
                description="\n".join(fw_desc),
                extra={"colour": "#64748b"},
            ))
        if fi_fw_items:
            fi_node["children"].append(_node(
                f"Firmware ({len(fi_fw_items)})", "group",
                children=fi_fw_items, extra={"colour": "#64748b"},
            ))

        # Attached domain/switch policies
        fi_serial = serial or ""
        fi_policies = self._fi_policy_map.get(fi_serial, [])
        fi_pol_node = self._build_policy_nodes(fi_policies)
        if fi_pol_node:
            fi_node["children"].append(fi_pol_node)

        return fi_node

    def _find_firmware(self, fi_dn: str, serial: str = "") -> str:
        for fw in self._mos.get("firmwareRunning", []):
            fw_dn = fw.get("dn", "")
            if fi_dn and fw_dn.startswith(fi_dn):
                return fw.get("version", "")
            if serial and serial in fw_dn:
                return fw.get("version", "")
        return ""

    def _find_mgmt_ip(self, switch_id: str, fi: dict | None = None) -> str:
        # Intersight: extIp is directly on the FI MO
        if fi:
            ip = fi.get("extIp", "") or fi.get("OutOfBandIpAddress", "")
            if ip and ip != "0.0.0.0":
                return ip
        for m in self._mos.get("mgmtIf", []):
            m_dn = m.get("dn", "")
            if f"switch-{switch_id}" in m_dn or f"sys-{switch_id}" in m_dn.upper():
                return m.get("extIp", "") or m.get("ip", "")
        return ""

    def _build_qos_section(self) -> dict:
        """Build system QoS classes display."""
        section = _node("QoS Classes", "group", extra={"colour": "#a78bfa"})
        qos_classes = self._mos.get("fabricQosClass", [])
        seen = set()
        for q in sorted(qos_classes, key=lambda x: _safe_int(x.get("cos", x.get("Cos", "0")))):
            name = q.get("name", q.get("Name", ""))
            cos = q.get("cos", q.get("Cos", ""))
            if name in seen:
                continue
            seen.add(name)
            admin = q.get("adminState", q.get("AdminState", ""))
            bw = q.get("bandwidthPercent", q.get("BandwidthPercent", q.get("bandwidth", "")))
            mtu = q.get("mtu", q.get("Mtu", ""))
            weight = q.get("weight", q.get("Weight", ""))
            pkt_drop = q.get("packetDrop", q.get("PacketDrop", ""))
            label = f"{name} (CoS {cos})"
            if admin and str(admin).lower() == "disabled":
                label += " [Disabled]"
            desc_parts = []
            if bw:
                desc_parts.append(f"BW: {bw}%")
            if mtu:
                desc_parts.append(f"MTU: {mtu}")
            if weight:
                desc_parts.append(f"Weight: {weight}")
            if pkt_drop != "":
                desc_parts.append(f"Drop: {'Yes' if str(pkt_drop).lower() in ('true','1','yes') else 'No'}")
            if admin:
                desc_parts.append(f"Admin: {admin}")
            colour = "#a78bfa" if admin and str(admin).lower() != "disabled" else "#6b7280"
            section["children"].append(_node(
                label, "qos_class",
                        description="\n".join(desc_parts),
                extra={"colour": colour},
            ))
        return section

    def _build_neighbor_section(self, switch_id: str) -> dict:
        """Build CDP/LLDP neighbor entries for a fabric interconnect."""
        section = _node("Neighbors", "group", extra={"colour": "#6b7280"})
        neighbors = self._mos.get("networkLanNeighborEntry", [])
        for n in neighbors:
            n_dn = n.get("dn", "")
            n_sid = n.get("switchId", "")
            serial_match = n_dn and f"switch-" in n_dn
            if n_sid:
                if n_sid.upper() != switch_id.upper():
                    continue
            elif serial_match:
                fi_serial = ""
                for fi in self._mos.get("networkElement", []):
                    if fi.get("switchId", "").upper() == switch_id.upper():
                        fi_serial = fi.get("serial", fi.get("Serial", ""))
                        break
                if fi_serial and fi_serial not in n_dn:
                    continue

            dev_id = n.get("devId", n.get("NeighborDeviceId", "?"))
            remote_port = n.get("remotePort", n.get("NeighborPortId", ""))
            local_port = n.get("localPort", n.get("SwitchPortId", ""))
            nbr_model = n.get("neighborModel", n.get("NeighborModel", ""))

            label = dev_id
            if local_port:
                label = f"{local_port} → {dev_id}"
            if remote_port:
                label += f" ({remote_port})"

            desc_parts = []
            if nbr_model and nbr_model != "-":
                desc_parts.append(f"Model: {nbr_model}")
            nbr_serial = n.get("neighborSerial", n.get("NeighborSerial", ""))
            if nbr_serial and nbr_serial != "-":
                desc_parts.append(f"Serial: {nbr_serial}")
            nbr_vendor = n.get("neighborVendor", n.get("NeighborVendor", ""))
            if nbr_vendor and nbr_vendor != "-":
                desc_parts.append(f"Vendor: {nbr_vendor}")
            mgmt = n.get("ManagementAddress", n.get("managementAddress", ""))
            if mgmt:
                desc_parts.append(f"IP: {mgmt}")
            nbr_cap = n.get("neighborCapability", n.get("NeighborCapability", ""))
            if nbr_cap and nbr_cap != "-":
                desc_parts.append(f"Capability: {nbr_cap}")
            nbr_nv = n.get("neighborNativeVlan", n.get("NeighborNativeVlan", ""))
            if nbr_nv:
                desc_parts.append(f"Native VLAN: {nbr_nv}")
            nbr_ver = n.get("neighborVersion", n.get("NeighborVersion", ""))
            if nbr_ver and nbr_ver != "-":
                desc_parts.append(f"Version: {nbr_ver}")

            section["children"].append(_node(
                label, "cdp_neighbor",
                        description="\n".join(desc_parts),
                extra={"colour": "#6b7280"},
            ))

        return section

    def _build_port_group(
        self, label: str, class_id: str, switch_id: str,
        port_type: str, disjoint_vlans: dict,
    ) -> dict:
        group = _node(label, "group", extra={"colour": _NODE_COLOURS.get(port_type, "#94a3b8")})

        ports = [
            p for p in self._mos.get(class_id, [])
            if p.get("switchId", "").upper() == switch_id.upper()
        ]

        for p in sorted(ports, key=lambda x: (
            _safe_int(x.get("slotId", "0")),
            _safe_int(x.get("portId", "0")),
        )):
            slot = p.get("slotId", "?")
            port_id = p.get("portId", "?")
            speed = p.get("adminSpeed", p.get("operSpeed", ""))
            state = p.get("operState", p.get("adminState", ""))
            peer = p.get("peerDn", "")

            port_label = f"Eth{slot}/{port_id}"
            desc_parts = []
            if speed:
                desc_parts.append(speed)
            if state:
                desc_parts.append(state)
            if peer:
                desc_parts.append(f"→ {peer}")

            port_node = _node(
                port_label, port_type,
                        description="\n".join(desc_parts),
                extra={"colour": _NODE_COLOURS.get(port_type, "#94a3b8")},
            )

            cdp = self._find_cdp_neighbor(switch_id, slot, port_id)
            if cdp:
                port_node["children"].append(cdp)

            vlan_children = self._port_vlan_membership(switch_id, slot, port_id, disjoint_vlans)
            if vlan_children:
                vlan_group = _node(
                    f"Allowed VLANs ({len(vlan_children)})", "group",
                    children=vlan_children, extra={"colour": "#3b82f6"},
                )
                port_node["children"].append(vlan_group)

            group["children"].append(port_node)

        return group

    def _build_fc_port_group(self, switch_id: str) -> dict:
        group = _node("FC Ports", "group", extra={"colour": "#c084fc"})

        ports = [
            p for p in self._mos.get("fabricFcSanEp", [])
            if p.get("switchId", "").upper() == switch_id.upper()
        ]

        for p in sorted(ports, key=lambda x: (
            _safe_int(x.get("slotId", "0")),
            _safe_int(x.get("portId", "0")),
        )):
            slot = p.get("slotId", "?")
            port_id = p.get("portId", "?")
            speed = p.get("adminSpeed", p.get("operSpeed", ""))
            state = p.get("operState", p.get("adminState", ""))
            vsan = p.get("portVsanId", "")

            label = f"fc{slot}/{port_id}"
            desc_parts = []
            if speed:
                desc_parts.append(speed)
            if state:
                desc_parts.append(state)
            if vsan:
                desc_parts.append(f"VSAN {vsan}")

            group["children"].append(_node(
                label, "fc_port",
                        description="\n".join(desc_parts),
                extra={"colour": "#c084fc"},
            ))

        return group

    def _build_port_channels(self, switch_id: str) -> dict:
        group = _node("Port Channels", "group", extra={"colour": "#67e8f9"})

        for class_id, prefix in [
            ("fabricEthLanPc", "Eth-PC"),
            ("fabricDceSwSrvPc", "Srv-PC"),
            ("fabricFcSanPc", "FC-PC"),
        ]:
            pcs = [
                pc for pc in self._mos.get(class_id, [])
                if pc.get("switchId", "").upper() == switch_id.upper()
            ]
            for pc in pcs:
                pc_id = pc.get("portId", pc.get("portChannelId", pc.get("id", "?")))
                state = pc.get("operState", pc.get("adminState", ""))
                speed = pc.get("operSpeed", pc.get("adminSpeed", pc.get("bandwidth", "")))
                role = pc.get("role", pc.get("Role", ""))

                label = f"{prefix}-{pc_id}"
                if role:
                    label += f" [{role}]"
                desc_parts = []
                if speed:
                    desc_parts.append(speed)
                if state:
                    desc_parts.append(state)

                members = self._find_pc_members(switch_id, pc_id, class_id)

                pc_node = _node(
                    label, "port_channel",
                    children=members,
                        description="\n".join(desc_parts),
                    extra={"colour": "#67e8f9"},
                )

                allowed = pc.get("allowedVlans", "")
                if allowed and allowed != "none":
                    vlan_ids = _expand_vlan_string(allowed)
                    pc_node["children"].append(_node(
                        f"Allowed VLANs ({len(vlan_ids)})", "vlan_list",
                        extra={
                            "colour": "#3b82f6",
                            "vlanIds": vlan_ids,
                            "vlanRanges": allowed,
                        },
                    ))

                group["children"].append(pc_node)

        return group

    def _find_pc_members(self, switch_id: str, pc_id: str, pc_class: str) -> list[dict]:
        member_class = {
            "fabricEthLanPc": "fabricEthLanPcEp",
            "fabricDceSwSrvPc": "fabricDceSwSrvPcEp",
        }.get(pc_class, "")

        if not member_class:
            return []

        members = []
        for ep in self._mos.get(member_class, []):
            if ep.get("switchId", "").upper() != switch_id.upper():
                continue
            dn = ep.get("dn", "")
            if f"pc-{pc_id}/" not in dn and f"pc-{pc_id}" not in dn.split("/"):
                continue
            slot = ep.get("slotId", "?")
            port = ep.get("portId", "?")
            members.append(_node(
                f"Eth{slot}/{port}", "uplink_port",
                extra={"colour": "#22d3ee"},
            ))
        return members

    def _find_cdp_neighbor(self, switch_id: str, slot: str, port_id: str) -> dict | None:
        for n in self._mos.get("networkLanNeighborEntry", []):
            n_dn = n.get("dn", "")
            if f"switch-{switch_id}" not in n_dn.upper() and f"switch-{switch_id}" not in n_dn:
                if f"sys/switch-{switch_id}" not in n_dn:
                    continue
            n_slot = n.get("fiSlotId", n.get("slotId", ""))
            n_port = n.get("fiPortId", n.get("portId", ""))
            if str(n_slot) == str(slot) and str(n_port) == str(port_id):
                device = n.get("deviceId", n.get("sysName", ""))
                remote_port = n.get("portId", n.get("remoteInterface", ""))
                platform = n.get("platform", "")
                mgmt_ip = n.get("ipV4MgmtAddress", n.get("mgmtIp", ""))

                label = f"CDP: {device}"
                if remote_port:
                    label += f" {remote_port}"

                desc_parts = []
                if platform:
                    desc_parts.append(platform)
                if mgmt_ip:
                    desc_parts.append(f"Mgmt: {mgmt_ip}")

                return _node(
                    label, "cdp_neighbor",
                        description="\n".join(desc_parts),
                    extra={"colour": "#94a3b8"},
                )
        return None

    def _port_vlan_membership(
        self, switch_id: str, slot: str, port_id: str, disjoint_vlans: dict,
    ) -> list[dict]:
        """Return VLAN child nodes for a given port, highlighting disjoint ones."""
        result: list[dict] = []

        for ep in self._mos.get("fabricEthVlanPortEp", []):
            if ep.get("switchId", "").upper() != switch_id.upper():
                continue
            ep_slot = ep.get("slotId", "")
            ep_port = ep.get("portId", "")
            if str(ep_slot) != str(slot) or str(ep_port) != str(port_id):
                continue

            vid = ep.get("vlanId", "") or self._vlan_id_from_dn(ep.get("dn", ""))
            vlan_name = ep.get("name", "")
            if not vid:
                continue

            is_disjoint = vid in disjoint_vlans
            label = f"VLAN {vid}"
            if vlan_name:
                label += f": {vlan_name}"
            if is_disjoint:
                label += " [DISJOINT]"

            result.append(_node(
                label,
                "disjoint_vlan" if is_disjoint else "vlan",
                extra={
                    "colour": "#dc2626" if is_disjoint else "#3b82f6",
                    "disjoint": is_disjoint,
                },
            ))

        result.sort(key=lambda n: int(
            n["name"].split()[1].split(":")[0]) if n["name"].split()[1].split(":")[0].isdigit() else 0
        )
        return result

    # ---- Physical chassis / rack ----

    def _build_chassis_physical(self) -> dict:
        section = _node("Chassis", "group", extra={"colour": "#f59e0b"})

        for ch in sorted(
            self._mos.get("equipmentChassis", []),
            key=lambda c: _safe_int(c.get("id", "0")),
        ):
            ch_id = ch.get("id", "?")
            model = ch.get("model", "")

            label = f"Chassis {ch_id}"
            if model:
                label += f" ({model})"

            ch_node = _node(label, "chassis",
                            description="\n".join(_mo_ident_parts(ch)) or "",
                            extra={"colour": "#f59e0b"})

            ioms = [
                io for io in self._mos.get("equipmentIOCard", [])
                if (io.get("dn", "").startswith(f"sys/chassis-{ch_id}/")
                    or io.get("dn", "").startswith(f"chassis-{ch_id}-ioc-")
                    or io.get("dn", "") == f"chassis-{ch_id}-ioc-{io.get('id', io.get('moduleId', ''))}")
            ]
            for io in sorted(ioms, key=lambda x: x.get("id", x.get("moduleId", ""))):
                io_id = io.get("id", io.get("moduleId", "?"))
                io_model = io.get("model", "")
                io_conn = io.get("connPath", io.get("ConnectionPath", ""))
                io_label = f"IOM-{io_conn or io_id}"
                if io_model:
                    io_label += f" ({io_model})"
                io_desc_parts = _mo_ident_parts(io)
                fw_ver = io.get("version", io.get("Version", ""))
                if fw_ver:
                    io_desc_parts.append(f"Firmware: {fw_ver}")
                io_conn_status = io.get("connStatus", io.get("ConnectionStatus", ""))
                if io_conn_status:
                    io_desc_parts.append(f"Connection: {io_conn_status}")
                io_side = io.get("side", io.get("Side", ""))
                if io_side:
                    io_desc_parts.append(f"Side: {io_side}")
                io_node = _node(
                    io_label, "iom",
                    description="\n".join(io_desc_parts),
                    extra={"colour": "#fb923c"},
                )
                if fw_ver:
                    io_node["children"].append(_node(
                        f"IOM FW: {fw_ver}", "firmware",
                        description=f"Type: IOM, Version: {fw_ver}",
                        extra={"colour": "#64748b"},
                    ))
                ch_node["children"].append(io_node)

            # PSUs
            psus = [
                p for p in self._mos.get("equipmentPsu", [])
                if f"chassis-{ch_id}-psu-" in p.get("dn", "")
                or p.get("dn", "").startswith(f"sys/chassis-{ch_id}/psu-")
            ]
            if psus:
                psu_group = _node(f"Power Supplies ({len(psus)})", "group", extra={"colour": "#eab308"})
                for ps in sorted(psus, key=lambda x: _safe_int(x.get("psuId", x.get("id", "0")))):
                    ps_id = ps.get("psuId", ps.get("id", "?"))
                    ps_model = ps.get("model", "")
                    ps_watt = ps.get("psuWattage", ps.get("PsuWattage", ""))
                    ps_label = f"PSU-{ps_id}"
                    if ps_model:
                        ps_label += f" ({ps_model})"
                    ps_desc = _mo_ident_parts(ps)
                    if ps_watt:
                        ps_desc.append(f"Wattage: {ps_watt}W")
                    ps_state = ps.get("operState", ps.get("OperState", ""))
                    if ps_state:
                        ps_desc.append(f"State: {ps_state}")
                    ps_type = ps.get("psuType", ps.get("PsuType", ""))
                    if ps_type:
                        ps_desc.append(f"Type: {ps_type}")
                    ps_input = ps.get("psuInputSrc", ps.get("PsuInputSrc", ""))
                    if ps_input:
                        ps_desc.append(f"Input: {ps_input}")
                    ps_fw = ps.get("psuFwVersion", ps.get("PsuFwVersion", ""))
                    if ps_fw:
                        ps_desc.append(f"FW: {ps_fw}")
                    psu_group["children"].append(_node(
                        ps_label, "psu",
                        description="\n".join(ps_desc),
                        extra={"colour": "#eab308"},
                    ))
                ch_node["children"].append(psu_group)

            # Fan modules
            fans = [
                fm for fm in self._mos.get("equipmentFanModule", [])
                if f"chassis-{ch_id}-" in fm.get("dn", "")
                or fm.get("dn", "").startswith(f"sys/chassis-{ch_id}/fan-module-")
            ]
            if fans:
                fan_group = _node(f"Fan Modules ({len(fans)})", "group", extra={"colour": "#a3e635"})
                for fan in sorted(fans, key=lambda x: _safe_int(x.get("moduleId", x.get("id", "0")))):
                    fan_mid = fan.get("moduleId", fan.get("id", "?"))
                    fan_model = fan.get("model", "")
                    fan_label = f"Fan-{fan_mid}"
                    if fan_model:
                        fan_label += f" ({fan_model})"
                    fan_desc = _mo_ident_parts(fan)
                    fan_state = fan.get("operState", fan.get("OperState", ""))
                    if fan_state:
                        fan_desc.append(f"State: {fan_state}")
                    fan_group["children"].append(_node(
                        fan_label, "fan",
                        description="\n".join(fan_desc),
                        extra={"colour": "#a3e635"},
                    ))
                ch_node["children"].append(fan_group)

            blades = [
                b for b in self._mos.get("computeBlade", [])
                if (b.get("dn", "").startswith(f"sys/chassis-{ch_id}/")
                    or b.get("chassisId", b.get("ChassisId", "")) == str(ch_id))
            ]
            if blades:
                blade_group = _node(f"Blades ({len(blades)})", "group", extra={"colour": "#34d399"})
                for b in sorted(blades, key=lambda x: _safe_int(x.get("slotId", "0"))):
                    blade_group["children"].append(self._build_server_hw_node(b, "blade"))
                ch_node["children"].append(blade_group)

            # Attached chassis policies
            ch_serial = _mo_serial(ch)
            ch_policies = self._chassis_policy_map.get(ch_serial, [])
            ch_pol_node = self._build_policy_nodes(ch_policies)
            if ch_pol_node:
                ch_node["children"].append(ch_pol_node)

            section["children"].append(ch_node)

        return section

    def _build_racks_physical(self) -> dict:
        section = _node("Rack Servers", "group", extra={"colour": "#34d399"})

        for r in sorted(
            self._mos.get("computeRackUnit", []),
            key=lambda x: _safe_int(x.get("serverId", x.get("id", "0"))),
        ):
            section["children"].append(self._build_server_hw_node(r, "rack_server"))

        return section

    def _build_server_hw_node(self, server: dict, ntype: str) -> dict:
        dn = server.get("dn", "")
        name = server.get("name", "")
        if ntype == "blade":
            slot = server.get("slotId", "?")
            label = f"Blade {slot}"
            if name:
                label = f"Blade {slot}: {name}"
        else:
            srv_id = server.get("serverId", server.get("id", "?"))
            label = f"Rack {srv_id}"
            if name:
                label = f"Rack {srv_id}: {name}"

        model = server.get("model", "")
        serial = _mo_serial(server)
        if model:
            label += f" ({model})"

        desc_parts = _mo_ident_parts(server)

        power = server.get("operPower", server.get("OperPowerState", ""))
        if power:
            desc_parts.append(f"Power: {power}")

        cpus = server.get("numOfCpus", server.get("NumCpus", ""))
        cores = server.get("numOfCores", server.get("NumCpuCores", ""))
        mem = server.get("totalMemory", server.get("TotalMemory", ""))
        if cpus and cores:
            desc_parts.append(f"CPUs: {cpus} ({cores} cores)")
        if mem:
            try:
                mem_gb = int(mem) // 1024
                if mem_gb > 0:
                    desc_parts.append(f"Memory: {mem_gb} GB")
            except (ValueError, TypeError):
                pass

        # Service profile association (from policy index or legacy DN)
        sp_info = (self._server_profile_info.get(serial)
                   or self._server_profile_info.get(server.get("Moid", ""))
                   or {})
        sp_name = sp_info.get("name", "")
        sp_template = sp_info.get("template", "")
        if not sp_name:
            assigned = server.get("assignedToDn", "")
            if assigned:
                sp_name = assigned.rsplit("/", 1)[-1].replace("ls-", "")
                # Also set dn in sp_info so fallback vNIC/vHBA matching can use it
                if not sp_info:
                    sp_info = {"name": sp_name, "dn": assigned, "moid": "", "template": ""}
                    # Try to find template from the lsServer MO
                    for ls in self._mos.get("lsServer", []):
                        ls_dn = ls.get("dn", "")
                        if ls_dn == assigned:
                            tmpl = ls.get("srcTempl", ls.get("operSrcTemplName", ""))
                            if tmpl:
                                sp_template = tmpl.rsplit("/", 1)[-1].replace("ls-", "", 1) if "/" in tmpl else tmpl
                                sp_info["template"] = sp_template
                            break
        # Easyimm fallback: resolve template name from easyimm data
        if not sp_template and sp_name and sp_name in self._easyimm_profiles:
            easyimm_prof = self._easyimm_profiles[sp_name]
            if easyimm_prof.get("template"):
                sp_template = easyimm_prof["template"]

        # If still no template, check if profile exists as a template itself
        if not sp_template and sp_name:
            for tname in self._easyimm_templates:
                if tname in sp_name or sp_name.startswith(tname.split("_")[0]):
                    continue

        if sp_name:
            desc_parts.append(f"Service Profile: {sp_name}")
            if sp_template:
                desc_parts.append(f"Derived from Template: {sp_template}")

        node = _node(label, ntype,
                     description="\n".join(desc_parts),
                     extra={"colour": _NODE_COLOURS.get(ntype, "#34d399")})

        # Add a Service Profile child node if we have profile info
        if sp_name:
            sp_desc = f"Profile: {sp_name}"
            if sp_template:
                sp_desc += f"\nDerived from Template: {sp_template}"
            profile_child = _node(
                f"Profile: {sp_name}", "server_profile",
                description=sp_desc,
                extra={"colour": "#10b981"},
            )
            if sp_template:
                profile_child["children"].append(_node(
                    f"Template: {sp_template}", "server_profile_template",
                    extra={"colour": "#8b5cf6"},
                ))
            node["children"].append(profile_child)

        # Match child MOs by DN prefix OR by parent serial/Moid
        moid = server.get("Moid", "")
        blade_serial = serial

        def _children_of(class_id: str) -> list[dict]:
            """Find child MOs belonging to this server."""
            results = []
            for mo in self._mos.get(class_id, []):
                mo_dn = mo.get("dn", "")
                # DN prefix match (UCSM style)
                if dn and mo_dn.startswith(dn + "/"):
                    results.append(mo)
                # Serial in DN (Intersight style: /redfish/v1/Systems/{serial}/...)
                elif blade_serial and blade_serial in mo_dn:
                    results.append(mo)
                # Parent Moid match
                elif moid and mo.get("_parent_ctx", {}).get("_parent_serial") == blade_serial:
                    results.append(mo)
            return results

        cpus = _children_of("processorUnit")
        if cpus:
            cpu_items = []
            for c in sorted(cpus, key=lambda x: _safe_int(x.get("id", "0"))):
                cmodel = c.get("model", c.get("Model", "CPU"))
                cores = c.get("cores", c.get("NumCores", ""))
                threads = c.get("threads", c.get("NumThreads", ""))
                speed = c.get("speed", c.get("Speed", ""))
                cpu_label = cmodel
                info = []
                if cores:
                    info.append(f"{cores}C")
                if threads:
                    info.append(f"{threads}T")
                if speed:
                    info.append(f"{speed}GHz")
                if info:
                    cpu_label += f" ({'/'.join(info)})"

                cpu_desc = []
                if cmodel:
                    cpu_desc.append(f"Model: {cmodel}")
                c_slot = c.get("SocketDesignation", c.get("socketDesignation", c.get("id", "")))
                if c_slot:
                    cpu_desc.append(f"Socket: {c_slot}")
                if cores:
                    cpu_desc.append(f"Cores: {cores}")
                if threads:
                    cpu_desc.append(f"Threads: {threads}")
                if speed:
                    cpu_desc.append(f"Speed: {speed} GHz")
                c_pid = c.get("Pid", c.get("pid", ""))
                if c_pid:
                    cpu_desc.append(f"PID: {c_pid}")
                c_pn = c.get("PartNumber", c.get("partNumber", ""))
                if c_pn:
                    cpu_desc.append(f"PN: {c_pn}")
                c_vendor = c.get("Vendor", c.get("vendor", ""))
                if c_vendor:
                    cpu_desc.append(f"Vendor: {c_vendor}")
                c_arch = c.get("Architecture", c.get("architecture", ""))
                if c_arch:
                    cpu_desc.append(f"Arch: {c_arch}")
                c_oper = c.get("OperState", c.get("operState", ""))
                if c_oper:
                    cpu_desc.append(f"State: {c_oper}")
                c_stepping = c.get("Stepping", c.get("stepping", ""))
                if c_stepping:
                    cpu_desc.append(f"Stepping: {c_stepping}")

                cpu_items.append(_node(cpu_label, "cpu",
                                       description="\n".join(cpu_desc),
                                       extra={"colour": "#818cf8"}))
            node["children"].append(_node(f"CPUs ({len(cpus)})", "group",
                                         children=cpu_items, extra={"colour": "#818cf8"}))

        # Memory DIMMs - grouped by processor lane and channel
        dimm_units = _children_of("memoryUnit")
        if dimm_units:
            import re as _re
            total_mb = 0
            dimm_count = 0
            # Parse DIMMs into {proc: {channel: [dimm_nodes]}}
            proc_channels: dict[str, dict[str, list]] = {}
            for dimm in sorted(dimm_units, key=lambda d: _safe_int(d.get("memoryId", d.get("MemoryId", d.get("id", "0"))))):
                cap_str = dimm.get("capacity", dimm.get("Capacity", "0"))
                cap_mb = _safe_int(cap_str)
                if cap_mb <= 0:
                    continue
                total_mb += cap_mb
                dimm_count += 1
                cap_gb = cap_mb // 1024

                slot_name = ""
                d_dn = dimm.get("dn", "")
                if "/Memory/" in d_dn:
                    slot_name = d_dn.rsplit("/Memory/", 1)[-1]
                elif "/memory-" in d_dn:
                    slot_name = d_dn.rsplit("/", 1)[-1]
                if not slot_name:
                    slot_name = f"DIMM_{dimm.get('memoryId', dimm.get('MemoryId', dimm.get('id', '?')))}"

                # Parse slot name like DIMM_P1_A2 or DIMM_P2_H1
                m = _re.match(r"DIMM_?(P\d+)_([A-Z])(\d+)", slot_name, _re.IGNORECASE)
                if m:
                    proc_key = m.group(1).upper()
                    chan_key = m.group(2).upper()
                else:
                    proc_key = "P1"
                    chan_key = "?"

                pn = dimm.get("partNumber", dimm.get("PartNumber", ""))
                d_type = dimm.get("type", dimm.get("Type", ""))
                d_form = dimm.get("formFactor", dimm.get("FormFactor", ""))
                d_speed = dimm.get("speed", dimm.get("Speed", ""))
                d_serial = dimm.get("serial", dimm.get("Serial", ""))

                d_desc = []
                if pn:
                    d_desc.append(f"PN: {pn}")
                if d_type:
                    d_desc.append(f"Type: {d_type}")
                if d_form:
                    d_desc.append(f"Form: {d_form}")
                if d_speed:
                    d_desc.append(f"Speed: {d_speed}")
                if d_serial:
                    d_desc.append(f"Serial: {d_serial}")

                dimm_node = _node(
                    f"{slot_name} ({cap_gb} GB)", "dimm",
                    description="\n".join(d_desc),
                    extra={"colour": "#34d399"},
                )
                proc_channels.setdefault(proc_key, {}).setdefault(chan_key, []).append((cap_mb, dimm_node))

            # Build hierarchy: Memory → P1/P2 → Channel A/B/... → DIMMs
            proc_items = []
            for proc_key in sorted(proc_channels):
                chan_items = []
                proc_mb = 0
                proc_dimm_count = 0
                for chan_key in sorted(proc_channels[proc_key]):
                    dimm_list = proc_channels[proc_key][chan_key]
                    chan_mb = sum(d[0] for d in dimm_list)
                    chan_nodes = [d[1] for d in dimm_list]
                    proc_mb += chan_mb
                    proc_dimm_count += len(chan_nodes)
                    chan_gb = chan_mb // 1024
                    chan_items.append(_node(
                        f"Channel {chan_key} ({chan_gb} GB / {len(chan_nodes)} DIMMs)",
                        "group", children=chan_nodes,
                        extra={"colour": "#34d399"},
                    ))
                proc_gb = proc_mb // 1024
                proc_items.append(_node(
                    f"{proc_key} ({proc_gb} GB / {proc_dimm_count} DIMMs)",
                    "group", children=chan_items,
                    extra={"colour": "#34d399"},
                ))

            total_gb = total_mb // 1024
            mem_label = f"Memory ({total_gb} GB / {dimm_count} DIMMs)"
            node["children"].append(_node(mem_label, "group",
                                         children=proc_items, extra={"colour": "#34d399"}))
        elif mem:
            try:
                mem_gb = int(mem) // 1024
                mem_speed = server.get("MemorySpeed", server.get("memorySpeed", ""))
                mem_label = f"Memory ({mem_gb} GB)"
                if mem_speed:
                    mem_label += f" @ {mem_speed} MT/s"
                node["children"].append(_node(mem_label, "memory", extra={"colour": "#34d399"}))
            except (ValueError, TypeError):
                pass

        adapters = _children_of("adaptorUnit")
        if adapters:
            # Build lookup: hostEthIf Moid -> Vethernet info (pinned uplink PC, VLANs)
            pc_vlans_by_dn = {}
            for pc in self._mos.get("fabricEthLanPc", []):
                pc_dn = pc.get("dn", "")
                if pc_dn and pc.get("allowedVlans"):
                    pc_vlans_by_dn[pc_dn] = pc["allowedVlans"]

            veth_by_adapter_moid: dict[str, dict] = {}
            for veth in self._mos.get("vnicEther", []):
                adapter_ref = veth.get("AdapterHostEthInterface")
                if isinstance(adapter_ref, dict):
                    aim = adapter_ref.get("Moid", "")
                    if aim:
                        pinned_dn = veth.get("PinnedInterfaceDn", veth.get("pinnedInterfaceDn", ""))
                        ratelimit = veth.get("Ratelimit", veth.get("ratelimit", ""))
                        burst = veth.get("Burst", veth.get("burst", ""))
                        veth_by_adapter_moid[aim] = {
                            "vethId": veth.get("VethId", veth.get("vethId", "")),
                            "pinnedPcDn": pinned_dn,
                            "operState": veth.get("OperState", veth.get("operState", "")),
                            "allowedVlans": pc_vlans_by_dn.get(pinned_dn, ""),
                            "ratelimit": ratelimit,
                            "burst": burst,
                        }

            # Profile-level values for vNIC/vHBA enrichment
            prof_moid = sp_info.get("moid", "") if sp_info else ""
            sp_name_for_match = sp_info.get("name", "") if sp_info else ""

            ad_items = []
            for a in sorted(adapters, key=lambda x: _safe_int(x.get("id", "0"))):
                amodel = a.get("model", a.get("Model", "Adapter"))
                a_desc = "\n".join(_mo_ident_parts(a))

                a_children: list[dict] = []
                a_dn = a.get("dn", "")
                a_moid = a.get("Moid", "")
                a_serial = _mo_serial(a)

                eth_ifs = [e for e in self._mos.get("adaptorExtEthIf", [])
                           if (a_dn and e.get("dn", "").startswith(a_dn + "/"))
                           or (a_serial and a_serial in e.get("dn", ""))
                           or (a_moid and e.get("_parent_ctx", {}).get("_parent_serial") == a_serial)]
                for e in eth_ifs:
                    mac = e.get("mac", e.get("MacAddress", ""))
                    ename = e.get("name", e.get("Name", "eth"))
                    a_children.append(_node(f"{ename} ({mac})" if mac else ename,
                                           "adapter", extra={"colour": "#f9a8d4"}))

                host_eths = [e for e in self._mos.get("adaptorHostEthIfProfile", [])
                             if (a_dn and e.get("dn", "").startswith(a_dn + "/"))
                             or (a_serial and a_serial in e.get("dn", ""))
                             or (a_moid and e.get("_parent_ctx", {}).get("_parent_serial") == a_serial)]
                for e in host_eths:
                    ename = e.get("name", e.get("Name", "vnic"))
                    mac = e.get("mac", e.get("MacAddress", ""))
                    e_moid = e.get("Moid", "")
                    veth_info = veth_by_adapter_moid.get(e_moid, {})

                    desc_parts = []
                    if mac:
                        desc_parts.append(f"MAC: {mac}")
                    oper = e.get("operState", e.get("OperState", ""))
                    if oper:
                        desc_parts.append(f"State: {oper}")
                    veth_id = veth_info.get("vethId", "")
                    if veth_id:
                        desc_parts.append(f"Veth: {veth_id}")
                    pinned = veth_info.get("pinnedPcDn", "")
                    if pinned:
                        desc_parts.append(f"Pinned: {pinned}")
                    rl = veth_info.get("ratelimit", "")
                    if rl:
                        try:
                            rl_mbps = int(rl)
                            if rl_mbps >= 1_000:
                                desc_parts.append(f"Rate: {rl_mbps // 1_000} Gbps")
                            else:
                                desc_parts.append(f"Rate: {rl_mbps} Mbps")
                        except (ValueError, TypeError):
                            desc_parts.append(f"Rate: {rl}")
                    burst_val = veth_info.get("burst", "")
                    if burst_val:
                        desc_parts.append(f"Burst: {burst_val}")

                    # Enrich with logical policy/pool/template info
                    vnic_logical = self._vnic_logical_map.get(
                        f"{prof_moid}:{ename}", {})

                    # Fallback 1: match UCSM-style vnicEther MOs with policy attributes
                    if not vnic_logical:
                        matched_vnic = None
                        for vnmo in self._mos.get("vnicEther", []):
                            vn_name = vnmo.get("name", vnmo.get("Name", ""))
                            if not vn_name or vn_name != ename:
                                continue
                            vn_dn = vnmo.get("dn", "")
                            sp_dn = sp_info.get("dn", "") if sp_info else ""
                            if sp_dn and vn_dn.startswith(sp_dn + "/"):
                                matched_vnic = vnmo
                                break
                            if sp_name_for_match and f"/ls-{sp_name_for_match}/" in vn_dn:
                                matched_vnic = vnmo
                                break
                            vn_prof = vnmo.get("Profile")
                            if isinstance(vn_prof, dict) and prof_moid and vn_prof.get("Moid") == prof_moid:
                                matched_vnic = vnmo
                                break
                        if matched_vnic:
                            for attr, plabel in (
                                ("identPoolName", "MAC Pool"),
                                ("nwTemplName", "vNIC Template"),
                                ("adaptorProfileName", "Adapter Policy"),
                                ("nwCtrlPolicyName", "Network Control"),
                                ("qosPolicyName", "QoS Policy"),
                            ):
                                val = matched_vnic.get(attr, "")
                                if val:
                                    vnic_logical[plabel] = val

                    # Fallback 2: use server-level policies from profile
                    if not vnic_logical and serial:
                        server_policies = (self._server_policy_map.get(serial)
                                           or self._server_policy_map.get(server.get("Moid", ""))
                                           or [])
                        for pol in server_policies:
                            ptype = pol.get("type", "")
                            pname = pol.get("name", "")
                            if "LAN" in ptype or "Lan" in ptype:
                                vnic_logical["LAN Connectivity"] = pname
                            elif "Adapter" in ptype and "Eth" in ptype:
                                vnic_logical["Eth Adapter Policy"] = pname
                            elif "QoS" in ptype and "Eth" in ptype:
                                vnic_logical["Eth QoS Policy"] = pname
                            elif "Network Group" in ptype:
                                vnic_logical["Eth Network Group Policy"] = pname
                            elif "Network Control" in ptype:
                                vnic_logical["Network Control"] = pname

                    _vnic_display_labels = (
                        "vNIC Template", "MAC Pool",
                        "LAN Connectivity",
                        "Eth Adapter Policy", "Adapter Policy",
                        "Eth QoS Policy", "QoS Policy",
                        "Eth Network Group Policy", "Network Control Policy",
                        "Network Control", "Eth Network Policy",
                    )

                    for pol_label in _vnic_display_labels:
                        pol_name = vnic_logical.get(pol_label, "")
                        if pol_name:
                            desc_parts.append(f"{pol_label}: {pol_name}")

                    vnic_node = _node(
                        f"vNIC: {ename}" + (f" ({mac})" if mac else ""),
                        "vnic",
                        description="\n".join(desc_parts),
                        extra={"colour": "#f472b6"},
                    )

                    # Add policy/pool/template child nodes under vNIC
                    for pol_label in _vnic_display_labels:
                        pol_name = vnic_logical.get(pol_label, "")
                        if pol_name:
                            ptype = "pool" if "Pool" in pol_label else ("server_profile_template" if "Template" in pol_label else "policy")
                            colour = "#06b6d4" if ptype == "pool" else ("#8b5cf6" if ptype == "server_profile_template" else "#a78bfa")
                            vnic_node["children"].append(_node(
                                f"{pol_label}: {pol_name}", ptype,
                                extra={"colour": colour},
                            ))

                    vlan_str = veth_info.get("allowedVlans", "")
                    if vlan_str:
                        vlan_ids = _expand_vlan_string(vlan_str)
                        vnic_node["children"].append(_node(
                            f"VLANs ({len(vlan_ids)})",
                            "vlan_list",
                            extra={
                                "colour": "#3b82f6",
                                "vlanIds": vlan_ids,
                                "vlanRanges": vlan_str,
                            },
                        ))

                    a_children.append(vnic_node)

                # Build Vfc lookup (like Vethernet but for FC)
                vfc_by_adapter_moid: dict[str, dict] = {}
                for vfc in self._mos.get("vnicFc", []):
                    fc_ref = vfc.get("AdapterHostFcInterface")
                    if isinstance(fc_ref, dict):
                        fc_aim = fc_ref.get("Moid", "")
                        if fc_aim:
                            vfc_by_adapter_moid[fc_aim] = {
                                "vfcId": vfc.get("VfcId", vfc.get("vfcId", "")),
                                "pinnedDn": vfc.get("PinnedInterfaceDn", vfc.get("pinnedInterfaceDn", "")),
                                "operState": vfc.get("OperState", vfc.get("operState", "")),
                                "ratelimit": vfc.get("Ratelimit", vfc.get("ratelimit", "")),
                                "burst": vfc.get("Burst", vfc.get("burst", "")),
                                "description": vfc.get("Description", vfc.get("description", "")),
                            }

                # Get VSAN from pinned FC physical port
                fc_port_vsan: dict[str, int] = {}
                for fcp in self._mos.get("fcPIo", []):
                    fcp_dn = fcp.get("dn", fcp.get("Dn", ""))
                    vsan = fcp.get("Vsan", fcp.get("vsan", ""))
                    if fcp_dn and vsan:
                        fc_port_vsan[fcp_dn] = vsan

                host_fcs = [f for f in self._mos.get("adaptorHostFcIfProfile", [])
                            if (a_dn and f.get("dn", "").startswith(a_dn + "/"))
                            or (a_serial and a_serial in f.get("dn", ""))
                            or (a_moid and f.get("_parent_ctx", {}).get("_parent_serial") == a_serial)]
                for fc in host_fcs:
                    fname = fc.get("name", fc.get("Name", "fc"))
                    wwpn = fc.get("wwn", fc.get("Wwpn", ""))
                    wwnn = fc.get("Wwnn", fc.get("wwnn", ""))
                    fc_moid = fc.get("Moid", "")
                    vfc_info = vfc_by_adapter_moid.get(fc_moid, {})

                    fc_desc_parts = []
                    if wwpn:
                        fc_desc_parts.append(f"WWPN: {wwpn}")
                    if wwnn:
                        fc_desc_parts.append(f"WWNN: {wwnn}")
                    vfc_oper = vfc_info.get("operState", "")
                    if vfc_oper:
                        fc_desc_parts.append(f"State: {vfc_oper}")
                    vfc_id = vfc_info.get("vfcId", "")
                    if vfc_id:
                        fc_desc_parts.append(f"Vfc: {vfc_id}")
                    pinned_fc = vfc_info.get("pinnedDn", "")
                    if pinned_fc:
                        fc_desc_parts.append(f"Pinned: {pinned_fc}")
                        vsan = fc_port_vsan.get(pinned_fc, "")
                        if vsan:
                            fc_desc_parts.append(f"VSAN: {vsan}")
                    fc_rl = vfc_info.get("ratelimit", "")
                    if fc_rl:
                        try:
                            rl_mbps = int(fc_rl)
                            if rl_mbps >= 1_000:
                                fc_desc_parts.append(f"Rate: {rl_mbps // 1_000} Gbps")
                            else:
                                fc_desc_parts.append(f"Rate: {rl_mbps} Mbps")
                        except (ValueError, TypeError):
                            pass

                    # Enrich with logical policy/pool info
                    vhba_logical = self._vhba_logical_map.get(
                        f"{prof_moid}:{fname}", {})

                    # Fallback 1: match UCSM-style vnicFc MOs
                    if not vhba_logical:
                        matched_vhba = None
                        for vfmo in self._mos.get("vnicFc", []):
                            vf_name = vfmo.get("name", vfmo.get("Name", ""))
                            if not vf_name or vf_name != fname:
                                continue
                            vf_dn = vfmo.get("dn", "")
                            sp_dn = sp_info.get("dn", "") if sp_info else ""
                            if sp_dn and vf_dn.startswith(sp_dn + "/"):
                                matched_vhba = vfmo
                                break
                            if sp_name_for_match and f"/ls-{sp_name_for_match}/" in vf_dn:
                                matched_vhba = vfmo
                                break
                            vf_prof = vfmo.get("Profile")
                            if isinstance(vf_prof, dict) and prof_moid and vf_prof.get("Moid") == prof_moid:
                                matched_vhba = vfmo
                                break
                        if matched_vhba:
                            for attr, plabel in (
                                ("identPoolName", "WWPN Pool"),
                                ("nwTemplName", "vHBA Template"),
                                ("adaptorProfileName", "FC Adapter Policy"),
                                ("qosPolicyName", "FC QoS Policy"),
                            ):
                                val = matched_vhba.get(attr, "")
                                if val:
                                    vhba_logical[plabel] = val

                    # Fallback 2: use server-level policies from profile
                    if not vhba_logical and serial:
                        server_policies = (self._server_policy_map.get(serial)
                                           or self._server_policy_map.get(server.get("Moid", ""))
                                           or [])
                        for pol in server_policies:
                            ptype = pol.get("type", "")
                            pname = pol.get("name", "")
                            if "SAN" in ptype or "San" in ptype:
                                vhba_logical["SAN Connectivity"] = pname
                            elif "Adapter" in ptype and "Fc" in ptype:
                                vhba_logical["FC Adapter Policy"] = pname
                            elif "QoS" in ptype and "Fc" in ptype:
                                vhba_logical["FC QoS Policy"] = pname
                            elif "FC Network" in ptype or "Fc Network" in ptype:
                                vhba_logical["FC Network Policy"] = pname

                    _vhba_display_labels = (
                        "vHBA Template", "WWPN Pool",
                        "WWNN Pool",
                        "SAN Connectivity",
                        "FC Adapter Policy", "FC QoS Policy",
                        "FC Network Policy",
                    )

                    for pol_label in _vhba_display_labels:
                        pol_name = vhba_logical.get(pol_label, "")
                        if pol_name:
                            fc_desc_parts.append(f"{pol_label}: {pol_name}")

                    vhba_node = _node(
                        f"vHBA: {fname}" + (f" ({wwpn})" if wwpn else ""),
                        "vhba",
                        description="\n".join(fc_desc_parts),
                        extra={"colour": "#f43f5e"},
                    )
                    # Add policy/pool/template child nodes under vHBA
                    for pol_label in _vhba_display_labels:
                        pol_name = vhba_logical.get(pol_label, "")
                        if pol_name:
                            ptype = "pool" if "Pool" in pol_label else ("server_profile_template" if "Template" in pol_label else "policy")
                            colour = "#06b6d4" if ptype == "pool" else ("#8b5cf6" if ptype == "server_profile_template" else "#a78bfa")
                            vhba_node["children"].append(_node(
                                f"{pol_label}: {pol_name}", ptype,
                                extra={"colour": colour},
                            ))
                    a_children.append(vhba_node)

                # Adapter firmware - match by adapter serial in firmware DN
                for fw_mo in self._mos.get("firmwareRunning", []):
                    fw_dn = fw_mo.get("dn", "")
                    fw_type = fw_mo.get("type", fw_mo.get("Type", ""))
                    if fw_type != "adaptor":
                        continue
                    if not (a_serial and a_serial in fw_dn):
                        continue
                    fw_comp = fw_mo.get("component", fw_mo.get("Component", ""))
                    if fw_comp == "boot-loader":
                        continue
                    fw_ver = fw_mo.get("version", fw_mo.get("Version", ""))
                    if fw_ver:
                        a_children.append(_node(
                            f"Adapter FW: {fw_ver}", "firmware",
                            description=f"Type: adaptor, Component: {fw_comp}, Version: {fw_ver}",
                            extra={"colour": "#64748b"},
                        ))

                ad_items.append(_node(amodel, "adapter",
                                      children=a_children,
                                      description=a_desc,
                                      extra={"colour": "#f472b6"}))
            node["children"].append(_node(f"Adapters ({len(adapters)})", "group",
                                         children=ad_items, extra={"colour": "#f472b6"}))

        # Storage controllers and disks
        controllers = _children_of("storageController")
        if controllers:
            stor_items = []
            for ctrl in sorted(controllers, key=lambda x: x.get("ControllerId", x.get("id", "0"))):
                ctrl_name = ctrl.get("Name", ctrl.get("name", ctrl.get("Model", ctrl.get("model", "Controller"))))
                ctrl_id = ctrl.get("ControllerId", ctrl.get("id", ""))
                ctrl_label = ctrl_name
                if ctrl_id and ctrl_id not in ctrl_name:
                    ctrl_label = f"{ctrl_id}: {ctrl_name}"
                ctrl_desc_parts = _mo_ident_parts(ctrl)
                ctrl_model = ctrl.get("Model", ctrl.get("model", ""))
                if ctrl_model and ctrl_model != ctrl_name:
                    ctrl_desc_parts.insert(0, f"Model: {ctrl_model}")
                ctrl_type = ctrl.get("Type", ctrl.get("type", ""))
                if ctrl_type:
                    ctrl_desc_parts.append(f"Type: {ctrl_type}")
                ctrl_raid = ctrl.get("RaidSupport", ctrl.get("raidSupport", ""))
                if ctrl_raid:
                    ctrl_desc_parts.append(f"RAID: {ctrl_raid}")
                ctrl_status = ctrl.get("ControllerStatus", ctrl.get("operState", ""))
                if ctrl_status:
                    ctrl_desc_parts.append(f"Status: {ctrl_status}")

                ctrl_dn = ctrl.get("dn", "")
                ctrl_moid = ctrl.get("Moid", "")
                ctrl_serial_val = ctrl.get("Serial", ctrl.get("serial", ""))

                disk_children = []
                for disk in self._mos.get("storageLocalDisk", []):
                    d_dn = disk.get("dn", disk.get("Dn", ""))
                    match = False
                    if ctrl_dn and d_dn.startswith(ctrl_dn):
                        match = True
                    elif blade_serial and blade_serial in d_dn:
                        match = True
                    elif ctrl_moid and disk.get("_parent_ctx", {}).get("_parent_serial") == ctrl_serial_val:
                        match = True
                    if not match:
                        continue

                    d_model = disk.get("Model", disk.get("model", "Disk"))
                    d_id = disk.get("DiskId", disk.get("id", ""))
                    d_size = disk.get("Size", disk.get("size", ""))
                    d_type = disk.get("Type", disk.get("type", ""))
                    d_proto = disk.get("Protocol", disk.get("protocol", ""))
                    d_state = disk.get("DiskState", disk.get("diskState", ""))

                    d_label = f"Disk {d_id}" if d_id else d_model
                    d_desc = _mo_ident_parts(disk)
                    if d_model:
                        d_desc.insert(0, f"Model: {d_model}")
                    if d_size:
                        try:
                            size_gb = int(d_size) // 1024
                            d_desc.append(f"Size: {size_gb} GB" if size_gb else f"Size: {d_size} MB")
                        except (ValueError, TypeError):
                            d_desc.append(f"Size: {d_size}")
                    if d_type:
                        d_desc.append(f"Type: {d_type}")
                    if d_proto:
                        d_desc.append(f"Protocol: {d_proto}")
                    if d_state:
                        d_desc.append(f"State: {d_state}")

                    disk_children.append(_node(
                        d_label, "disk",
                        description="\n".join(d_desc),
                        extra={"colour": "#fbbf24"},
                    ))

                stor_items.append(_node(
                    ctrl_label, "storage_controller",
                    children=disk_children,
                    description="\n".join(ctrl_desc_parts),
                    extra={"colour": "#fbbf24"},
                ))
            node["children"].append(_node(
                f"Storage ({len(controllers)})", "group",
                children=stor_items, extra={"colour": "#fbbf24"},
            ))

        # Firmware versions for this server
        fw_items = []
        _fw_labels = {
            "blade-bios": "BIOS",
            "blade-controller": "CIMC",
            "adaptor": "Adapter FW",
            "switch-software": "Switch SW",
        }
        for fw in self._mos.get("firmwareRunning", []):
            fw_dn = fw.get("dn", "")
            if not (blade_serial and blade_serial in fw_dn):
                continue
            fw_type = fw.get("type", fw.get("Type", ""))
            fw_ver = fw.get("version", fw.get("Version", ""))
            fw_comp = fw.get("component", fw.get("Component", ""))
            if not fw_ver or fw_comp == "boot-loader":
                continue
            fw_label_prefix = _fw_labels.get(fw_type, fw_type or "Firmware")
            fw_label = f"{fw_label_prefix}: {fw_ver}"
            fw_desc_parts = []
            if fw_type:
                fw_desc_parts.append(f"Type: {fw_type}")
            if fw_comp:
                fw_desc_parts.append(f"Component: {fw_comp}")
            fw_desc_parts.append(f"Version: {fw_ver}")
            pkg_ver = fw.get("packageVersion", fw.get("PackageVersion", ""))
            if pkg_ver and pkg_ver != fw_ver:
                fw_desc_parts.append(f"Package: {pkg_ver}")
            fw_items.append(_node(
                fw_label, "firmware",
                description="\n".join(fw_desc_parts),
                extra={"colour": "#64748b"},
            ))
        if fw_items:
            node["children"].append(_node(
                f"Firmware ({len(fw_items)})", "group",
                children=fw_items, extra={"colour": "#64748b"},
            ))

        # Alarm summary from AlarmSummary dict
        alarm = server.get("AlarmSummary")
        if isinstance(alarm, dict):
            crit = _safe_int(alarm.get("Critical", "0"))
            warn = _safe_int(alarm.get("Warning", "0"))
            health = alarm.get("Health", "")
            if crit or warn:
                alarm_desc = f"Health: {health}, Critical: {crit}, Warning: {warn}"
                alarm_colour = "#dc2626" if crit else "#f97316"
                node["children"].append(_node(
                    f"Alarms (Critical: {crit}, Warning: {warn})",
                    "alarm", description=alarm_desc,
                    extra={"colour": alarm_colour},
                ))

        # Fault summary (numeric from FaultSummary field)
        fault_count = _safe_int(server.get("faultSummary", "0"))
        if fault_count > 0:
            node["children"].append(_node(
                f"Faults ({fault_count})", "alarm",
                description=f"Total faults reported: {fault_count}",
                extra={"colour": "#f97316"},
            ))

        # Attached policies (from server profile's PolicyBucket)
        blade_serial = serial or ""
        policies = self._server_policy_map.get(blade_serial, [])
        if not policies and moid:
            policies = self._server_policy_map.get(moid, [])
        if not policies:
            _sp_name = sp_name or server.get("assignedToDn", "") or server.get("name", "")
            if _sp_name:
                policies = self._profile_name_policy_map.get(_sp_name, [])
        pol_node = self._build_policy_nodes(policies)
        if pol_node:
            node["children"].append(pol_node)

        # KVM IP from inline attribute
        kvm_ip = server.get("mgmtIpAddress", server.get("MgmtIpAddress", ""))
        if kvm_ip and kvm_ip != "0.0.0.0":
            node["children"].append(_node(f"KVM: {kvm_ip}", "mgmt",
                                         extra={"colour": "#0ea5e9"}))

        return node

    # ---- Physical VLANs / VSANs with disjoint highlighting ----

    def _build_vlans_physical(self, disjoint_vlans: dict) -> dict:
        vlans = self._mos.get("fabricVlan", [])
        group = _node(f"All VLANs ({len(vlans)})", "group", extra={"colour": "#3b82f6"})

        for v in sorted(vlans, key=lambda x: int(x.get("id", "0") or "0")):
            vid = v.get("id", "?")
            name = v.get("name", "")
            sid = v.get("switchId", "dual")
            is_disjoint = vid in disjoint_vlans

            label = f"VLAN {vid}"
            if name:
                label += f": {name}"
            label += f" ({sid})"
            if is_disjoint:
                label += " [DISJOINT]"

            group["children"].append(_node(
                label,
                "disjoint_vlan" if is_disjoint else "vlan",
                extra={
                    "colour": "#dc2626" if is_disjoint else "#3b82f6",
                    "disjoint": is_disjoint,
                },
            ))

        return group

    def _build_vsans_physical(self) -> dict:
        vsans = self._mos.get("fabricVsan", [])
        group = _node(f"All VSANs ({len(vsans)})", "group", extra={"colour": "#8b5cf6"})

        for v in sorted(vsans, key=lambda x: int(x.get("id", "0") or "0")):
            vid = v.get("id", "?")
            name = v.get("name", "")
            sid = v.get("switchId", "")
            fc_zone = v.get("fcoeVlan", v.get("fcZoneSharingMode", ""))

            label = f"VSAN {vid}"
            if name:
                label += f": {name}"
            desc_parts = []
            if sid:
                desc_parts.append(f"Fabric {sid}")
            if fc_zone:
                desc_parts.append(f"FCoE: {fc_zone}")

            group["children"].append(_node(
                label, "vsan",
                        description="\n".join(desc_parts),
                extra={"colour": "#8b5cf6"},
            ))

        return group

    # ====================================================================
    # Errors tree builder (fault correlation)
    # ====================================================================

    _SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, "warning": 3, "info": 4, "cleared": 5}
    _SEVERITY_COLOURS = {
        "critical": "#dc2626",
        "major": "#f97316",
        "minor": "#eab308",
        "warning": "#64748b",
        "info": "#94a3b8",
        "cleared": "#475569",
    }
    _SEVERITY_TYPES = {
        "critical": "error_critical",
        "major": "error_major",
        "minor": "error_minor",
        "warning": "error_warning",
        "info": "error_info",
        "cleared": "error_info",
    }

    _FAULT_PATTERNS: list[tuple[list[str], str, str]] = [
        (["boot", "pxe", "lan-fail"], "Boot Failure",
         "Check boot policy VLAN references and boot order configuration"),
        (["link-down", "link-fail", "oper-state"], "Link Down",
         "Check physical cabling and upstream switch port status"),
        (["discovery", "discover"], "Discovery Issue",
         "Acknowledge faults and re-trigger chassis/server discovery"),
        (["power", "psu", "power-budget"], "Power Issue",
         "Check PSU status and power budget; consider power redundancy policy"),
        (["thermal", "fan", "temp"], "Thermal Issue",
         "Check fan modules and ambient temperature; inspect air flow"),
        (["config-failure", "config-error", "apply-fail"], "Configuration Failure",
         "Review service profile policy references and reapply configuration"),
        (["fsm", "finite-state"], "FSM Failure",
         "Monitor FSM state; retry operation or acknowledge if stuck"),
        (["dimm", "memory", "mem-"], "Memory Issue",
         "Run diagnostics on reported DIMMs; consider replacement"),
        (["adapter", "nic", "hba", "vif"], "Adapter Issue",
         "Check adapter firmware and driver compatibility; reseat if needed"),
        (["storage", "disk", "raid", "lun"], "Storage Issue",
         "Check disk health, RAID status, and storage controller logs"),
        (["license"], "License Issue",
         "Verify license compliance on intersight.com or UCSM"),
        (["certificate", "cert"], "Certificate Issue",
         "Renew or install valid certificates; check expiration dates"),
        (["connectivity", "unreachable", "timeout"], "Connectivity Issue",
         "Check network reachability, DNS, NTP, and management interface status"),
    ]

    def _build_errors_tree(self) -> dict:
        root = _node(f"Errors: {self._filename}", "root")
        root["colours"] = _NODE_COLOURS
        root["categoryColours"] = self._SEVERITY_COLOURS
        root["source"] = "techsupport"
        root["view"] = "errors"

        faults = self._mos.get("faultInst", [])
        if not faults:
            root["children"].append(_node(
                "No faults found", "group",
                description="The techsupport bundle contains no faultInst MOs",
                extra={"colour": "#10b981"},
            ))
            return root

        groups = self._correlate_faults(faults)

        by_severity: dict[str, list[dict]] = {}
        for g in groups:
            sev = g["severity"]
            by_severity.setdefault(sev, []).append(g)

        for sev in ["critical", "major", "minor", "warning", "info", "cleared"]:
            sev_groups = by_severity.get(sev, [])
            if not sev_groups:
                continue

            colour = self._SEVERITY_COLOURS.get(sev, "#94a3b8")
            ntype = self._SEVERITY_TYPES.get(sev, "error_info")
            sev_label = f"{sev.capitalize()} ({len(sev_groups)} issue{'s' if len(sev_groups) != 1 else ''})"
            sev_node = _node(sev_label, ntype, extra={"colour": colour, "severity": sev})

            for g in sev_groups:
                issue_node = _node(
                    g["title"], ntype,
                    description=g.get("description", ""),
                    extra={"colour": colour, "severity": sev},
                )

                if g.get("root_cause"):
                    issue_node["children"].append(_node(
                        f"Root Cause: {g['root_cause']}", "root_cause",
                        extra={"colour": "#f59e0b"},
                    ))

                if len(g["faults"]) > 1:
                    related = _node(
                        f"Related Faults ({len(g['faults'])})", "group",
                        extra={"colour": "#475569"},
                    )
                    for f in g["faults"]:
                        code = f.get("code", "?")
                        cause = f.get("cause", "")
                        descr = f.get("descr", "")
                        f_dn = f.get("dn", "")
                        f_label = f"{code}: {cause}" if cause else code
                        related["children"].append(_node(
                            f_label, "fault",
                            description=f"{descr}\n{f_dn}" if descr else f_dn,
                            extra={"colour": "#94a3b8"},
                        ))
                    issue_node["children"].append(related)
                else:
                    f = g["faults"][0]
                    descr = f.get("descr", "")
                    if descr:
                        issue_node["description"] = descr

                if g.get("action"):
                    issue_node["children"].append(_node(
                        f"Action: {g['action']}", "action",
                        extra={"colour": "#10b981"},
                    ))

                sev_node["children"].append(issue_node)

            root["children"].append(sev_node)

        total = sum(len(v) for v in by_severity.values())
        root["name"] = f"Errors: {self._filename} ({total} issues from {len(faults)} faults)"

        return root

    def _correlate_faults(self, faults: list[dict]) -> list[dict]:
        """Group faults by parent DN component, classify, and produce insight groups."""

        active = [f for f in faults if f.get("severity", "").lower() not in ("cleared",)]
        if not active:
            active = faults

        by_component: dict[str, list[dict]] = {}
        for f in active:
            dn = f.get("dn", "")
            component = self._fault_component(dn)
            by_component.setdefault(component, []).append(f)

        groups: list[dict] = []
        for component, comp_faults in by_component.items():
            comp_faults.sort(
                key=lambda x: self._SEVERITY_ORDER.get(x.get("severity", "info").lower(), 99)
            )
            lead = comp_faults[0]
            severity = lead.get("severity", "info").lower()

            pattern_name, action = self._classify_faults(comp_faults)
            root_cause = self._derive_root_cause(comp_faults, pattern_name)

            friendly = self._friendly_component(component)
            title = f"{pattern_name} — {friendly}" if pattern_name != "General Fault" else friendly

            groups.append({
                "title": title,
                "severity": severity,
                "component": component,
                "root_cause": root_cause,
                "action": action,
                "description": lead.get("descr", ""),
                "faults": comp_faults,
            })

        groups.sort(key=lambda g: self._SEVERITY_ORDER.get(g["severity"], 99))
        return groups

    @staticmethod
    def _fault_component(dn: str) -> str:
        """Extract parent component from a fault DN (strip /fault-xxx suffix)."""
        parts = dn.split("/")
        non_fault = [p for p in parts if not p.startswith("fault-")]
        return "/".join(non_fault) if non_fault else dn

    @staticmethod
    def _friendly_component(component: str) -> str:
        parts = component.split("/")
        friendly_parts = []
        for p in parts:
            if p == "sys":
                continue
            if p.startswith("chassis-"):
                friendly_parts.append(f"Chassis {p.replace('chassis-', '')}")
            elif p.startswith("blade-"):
                friendly_parts.append(f"Blade {p.replace('blade-', '')}")
            elif p.startswith("switch-"):
                friendly_parts.append(f"FI-{p.replace('switch-', '')}")
            elif p.startswith("rack-unit-"):
                friendly_parts.append(f"Rack {p.replace('rack-unit-', '')}")
            elif p.startswith("ls-"):
                friendly_parts.append(p.replace("ls-", "SP:"))
            elif p.startswith("org-"):
                friendly_parts.append(p.replace("org-", ""))
            elif p.startswith("slot-"):
                friendly_parts.append(f"Slot {p.replace('slot-', '')}")
            elif p.startswith("port-"):
                friendly_parts.append(f"Port {p.replace('port-', '')}")
            else:
                friendly_parts.append(p)
        return " / ".join(friendly_parts) if friendly_parts else component

    def _classify_faults(self, faults: list[dict]) -> tuple[str, str]:
        """Match fault group against known patterns; return (pattern_name, recommended_action)."""
        combined = " ".join(
            f"{f.get('cause', '')} {f.get('descr', '')} {f.get('code', '')}".lower()
            for f in faults
        )
        for keywords, name, action in self._FAULT_PATTERNS:
            if any(kw in combined for kw in keywords):
                return name, action
        return "General Fault", "Investigate the reported fault details and take corrective action"

    @staticmethod
    def _derive_root_cause(faults: list[dict], pattern_name: str) -> str:
        """Attempt to derive a root cause summary from the fault group."""
        lead = faults[0]
        cause = lead.get("cause", "")
        descr = lead.get("descr", "")

        if pattern_name == "Boot Failure":
            return descr or cause or "Server failed to boot from configured boot source"
        if pattern_name == "Link Down":
            return cause or "Physical link is operationally down"
        if pattern_name == "Discovery Issue":
            return descr or "Component discovery did not complete successfully"
        if pattern_name == "Configuration Failure":
            return descr or "Service profile or policy configuration could not be applied"
        if pattern_name == "Power Issue":
            return descr or "Power supply or power budget anomaly detected"
        if pattern_name == "Thermal Issue":
            return descr or "Temperature or fan speed threshold exceeded"

        return cause or descr or ""

    # ---- Topology view: Server → IOM → FI traffic paths ----

    def _build_topology_tree(self) -> dict:
        """Build a topology tree showing traffic paths from servers through IOMs to FIs."""
        root = _node(f"Topology: {self._filename}", "root")
        root["colours"] = _NODE_COLOURS
        root["source"] = "techsupport"
        root["view"] = "topology"

        fis = self._mos.get("networkElement", [])
        if not fis:
            root["children"].append(_node("No Fabric Interconnects found", "info"))
            return root

        # Build FI lookup
        fi_by_serial: dict[str, dict] = {}
        fi_by_id: dict[str, dict] = {}
        for fi in fis:
            sid = fi.get("switchId", fi.get("id", "?"))
            serial = fi.get("serial", "")
            fi_by_id[sid.upper()] = fi
            if serial:
                fi_by_serial[serial] = fi

        # Build port channel lookup: DN → {id, allowedVlans, operSpeed, role}
        pc_info: dict[str, dict] = {}
        for pc in self._mos.get("fabricEthLanPc", []):
            pc_dn = pc.get("dn", "")
            if pc_dn:
                pc_info[pc_dn] = {
                    "id": pc.get("portId", pc.get("portChannelId", "")),
                    "vlans": pc.get("allowedVlans", ""),
                    "speed": pc.get("operSpeed", pc.get("adminSpeed", "")),
                    "role": pc.get("role", pc.get("Role", "")),
                    "bandwidth": pc.get("bandwidth", pc.get("BandWidth", "")),
                }

        # Build PC member lookup: "switchId-pcId" → list of "Eth slot/port (speed)"
        pc_members: dict[str, list[str]] = defaultdict(list)
        for phys_port in self._mos.get("etherPIo", []):
            pcid = phys_port.get("portChannelId", phys_port.get("PortChannelId", ""))
            sid = phys_port.get("switchId", phys_port.get("SwitchId", ""))
            slot = phys_port.get("slotId", phys_port.get("SlotId", ""))
            port = phys_port.get("portId", phys_port.get("PortId", ""))
            p_speed = phys_port.get("operSpeed", phys_port.get("OperSpeed", ""))
            if pcid and pcid != "0" and sid:
                member_str = f"Eth{slot}/{port}"
                if p_speed:
                    member_str += f" ({p_speed})"
                pc_members[f"{sid}-{pcid}"].append(member_str)

        # Build FC physical port lookup: DN → readable label
        fc_port_labels: dict[str, str] = {}
        fc_port_vsan_topo: dict[str, str] = {}
        for fcp in self._mos.get("fcPIo", []):
            fcp_dn = fcp.get("dn", fcp.get("Dn", ""))
            slot = fcp.get("slotId", fcp.get("SlotId", ""))
            port = fcp.get("portId", fcp.get("PortId", ""))
            aggr = fcp.get("aggrPortId", fcp.get("AggregatePortId", ""))
            vsan = fcp.get("Vsan", fcp.get("vsan", ""))
            speed = fcp.get("operSpeed", fcp.get("OperSpeed", ""))
            if fcp_dn:
                label = f"FC{slot}/{aggr}/{port}" if aggr and aggr != "0" else f"FC{slot}/{port}"
                if speed:
                    label += f" ({speed})"
                fc_port_labels[fcp_dn] = label
                if vsan:
                    fc_port_vsan_topo[fcp_dn] = str(vsan)

        # Build Vethernet lookup: server serial → list of veth info
        server_veths: dict[str, list] = defaultdict(list)
        for veth in self._mos.get("vnicEther", []):
            desc = veth.get("Description", veth.get("description", ""))
            pinned = veth.get("PinnedInterfaceDn", veth.get("pinnedInterfaceDn", ""))
            bound = veth.get("BoundInterfaceDn", veth.get("boundInterfaceDn", ""))
            # Extract blade serial from description: "SP xxx, vNIC yyy, Blade:FCH..."
            blade_serial = ""
            if "Blade:" in desc:
                blade_serial = desc.split("Blade:")[-1].strip()
            elif "Server:" in desc:
                blade_serial = desc.split("Server:")[-1].strip()
            # Extract vNIC name and SP name from description
            vnic_name = ""
            sp_name = ""
            if "vNIC " in desc:
                parts = desc.split("vNIC ")
                if len(parts) > 1:
                    vnic_name = parts[1].split(",")[0].strip()
            if "SP " in desc:
                parts = desc.split("SP ")
                if len(parts) > 1:
                    sp_name = parts[1].split(",")[0].strip()

            adapter_ref = veth.get("AdapterHostEthInterface")
            adapter_moid = adapter_ref.get("Moid", "") if isinstance(adapter_ref, dict) else ""

            if blade_serial:
                server_veths[blade_serial].append({
                    "vnic": vnic_name,
                    "sp": sp_name,
                    "pinned": pinned,
                    "bound": bound,
                    "operState": veth.get("OperState", veth.get("operState", "")),
                    "ratelimit": veth.get("Ratelimit", veth.get("ratelimit", "")),
                    "vethId": veth.get("VethId", veth.get("vethId", "")),
                    "type": "vNIC",
                    "adapter_moid": adapter_moid,
                })

        # Build Vfc lookup
        server_vfcs: dict[str, list] = defaultdict(list)
        fc_port_vsan: dict[str, str] = {}
        for fcp in self._mos.get("fcPIo", []):
            fcp_dn = fcp.get("dn", fcp.get("Dn", ""))
            vsan = fcp.get("Vsan", fcp.get("vsan", ""))
            if fcp_dn and vsan:
                fc_port_vsan[fcp_dn] = str(vsan)

        for vfc in self._mos.get("vnicFc", []):
            desc = vfc.get("Description", vfc.get("description", ""))
            pinned = vfc.get("PinnedInterfaceDn", vfc.get("pinnedInterfaceDn", ""))
            bound = vfc.get("BoundInterfaceDn", vfc.get("boundInterfaceDn", ""))
            blade_serial = ""
            if "Blade:" in desc:
                blade_serial = desc.split("Blade:")[-1].strip()
            elif "Server:" in desc:
                blade_serial = desc.split("Server:")[-1].strip()
            vhba_name = ""
            if "vHBA " in desc:
                parts = desc.split("vHBA ")
                if len(parts) > 1:
                    vhba_name = parts[1].split(",")[0].strip()
            sp_name = ""
            if "SP " in desc:
                parts = desc.split("SP ")
                if len(parts) > 1:
                    sp_name = parts[1].split(",")[0].strip()

            if blade_serial:
                vsan_id = fc_port_vsan.get(pinned, "")
                server_vfcs[blade_serial].append({
                    "vhba": vhba_name,
                    "sp": sp_name,
                    "pinned": pinned,
                    "bound": bound,
                    "vsan": vsan_id,
                    "operState": vfc.get("OperState", vfc.get("operState", "")),
                    "vfcId": vfc.get("VfcId", vfc.get("vfcId", "")),
                    "type": "vHBA",
                })

        # IOM lookup: chassisId + side → IOM info
        iom_lookup: dict[str, dict] = {}
        for io in self._mos.get("equipmentIOCard", []):
            ch_id = ""
            io_dn = io.get("dn", "")
            if io_dn.startswith("sys/chassis-"):
                ch_id = io_dn.split("/")[1].replace("chassis-", "")
            elif "chassis-" in io_dn:
                import re
                m = re.search(r"chassis-(\d+)", io_dn)
                if m:
                    ch_id = m.group(1)
            side = io.get("connPath", io.get("ConnectionPath", io.get("id", "")))
            if ch_id and side:
                iom_lookup[f"{ch_id}-{side}"] = io

        # Build topology per chassis
        for ch in sorted(
            self._mos.get("equipmentChassis", []),
            key=lambda c: _safe_int(c.get("id", "0")),
        ):
            ch_id = ch.get("id", "?")
            ch_model = ch.get("model", "")
            ch_node = _node(
                f"Chassis {ch_id}" + (f" ({ch_model})" if ch_model else ""),
                "chassis",
                extra={"colour": "#f59e0b"},
            )

            blades = [
                b for b in self._mos.get("computeBlade", [])
                if (b.get("dn", "").startswith(f"sys/chassis-{ch_id}/")
                    or b.get("chassisId", b.get("ChassisId", "")) == str(ch_id))
            ]
            for blade in sorted(blades, key=lambda x: _safe_int(x.get("slotId", "0"))):
                slot = blade.get("slotId", "?")
                b_name = blade.get("name", "")
                b_model = blade.get("model", "")
                b_serial = blade.get("serial", "")
                b_label = f"Blade {slot}"
                if b_name:
                    b_label += f": {b_name}"
                if b_model:
                    b_label += f" ({b_model})"

                b_node = _node(b_label, "blade",
                               description=f"Serial: {b_serial}" if b_serial else "",
                               extra={"colour": "#34d399"})

                # Group paths by FI side (A/B)
                paths_by_side: dict[str, list] = defaultdict(list)
                all_paths = list(server_veths.get(b_serial, [])) + list(server_vfcs.get(b_serial, []))
                for path in all_paths:
                    pinned = path.get("pinned", "")
                    fi_side = ""
                    for fi_serial, fi_obj in fi_by_serial.items():
                        if fi_serial in pinned:
                            fi_side = fi_obj.get("switchId", fi_obj.get("id", "?"))
                            break
                    if not fi_side:
                        fi_side = "?"
                    paths_by_side[fi_side.upper()].append(path)

                for side in sorted(paths_by_side):
                    side_paths = paths_by_side[side]
                    iom_key = f"{ch_id}-{side}"
                    iom = iom_lookup.get(iom_key, {})
                    iom_model = iom.get("model", "")
                    iom_label = f"→ IOM-{side}"
                    if iom_model:
                        iom_label += f" ({iom_model})"

                    fi = fi_by_id.get(side, {})
                    fi_model = fi.get("model", "")
                    fi_label = f"→ FI-{side}"
                    if fi_model:
                        fi_label += f" ({fi_model})"

                    iom_node = _node(iom_label, "iom", extra={"colour": "#fb923c"})

                    # Group vNICs by their pinned port channel
                    pc_groups: dict[str, list] = defaultdict(list)
                    for p in side_paths:
                        pc_groups[p.get("pinned", "direct")].append(p)

                    fi_children = []
                    for pc_dn, items in sorted(pc_groups.items()):
                        pc = pc_info.get(pc_dn, {})
                        pc_id = pc.get("id", "")
                        pc_speed = pc.get("speed", "")
                        pc_vlans_str = pc.get("vlans", "")
                        pc_role = pc.get("role", "")
                        pc_bw = pc.get("bandwidth", "")

                        is_fc = any(p["type"] == "vHBA" for p in items)

                        if is_fc:
                            # FC path: use the actual FC port label
                            fc_dn = items[0].get("pinned", "") if items else ""
                            fc_label = fc_port_labels.get(fc_dn, "")
                            if fc_label:
                                pc_label = fc_label
                            elif "port-" in fc_dn:
                                pc_label = fc_dn.split("/")[-1]
                            else:
                                pc_label = fc_dn
                            fc_vsan = fc_port_vsan_topo.get(fc_dn, "")
                            if fc_vsan:
                                pc_label += f" [VSAN {fc_vsan}]"
                        elif pc_id:
                            pc_label = f"Port-Channel {pc_id}"
                        elif "pc-" in pc_dn:
                            pc_label = f"PC {pc_dn.split('pc-')[-1]}"
                        else:
                            pc_label = pc_dn.split("/")[-1] if "/" in pc_dn else pc_dn

                        pc_desc = []
                        if pc_role:
                            pc_desc.append(f"Role: {pc_role}")
                        if pc_speed:
                            pc_desc.append(f"Speed: {pc_speed}")
                        if pc_bw:
                            pc_desc.append(f"Bandwidth: {pc_bw}")

                        # Add member interfaces for Ethernet PCs
                        if pc_id and not is_fc:
                            member_key = f"{side}-{pc_id}"
                            members = pc_members.get(member_key, [])
                            if members:
                                pc_desc.append(f"Members: {', '.join(sorted(members))}")

                        vnic_names = [p.get("vnic") or p.get("vhba", "") for p in items]
                        types = set(p["type"] for p in items)
                        type_str = "/".join(sorted(types))
                        pc_desc.append(f"{type_str}s: {', '.join(n for n in vnic_names if n)}")

                        pc_colour = "#c084fc" if is_fc else "#67e8f9"
                        pc_node = _node(pc_label, "port_channel" if not is_fc else "fc_port",
                                        description="\n".join(pc_desc),
                                        extra={"colour": pc_colour})

                        for p in items:
                            if p["type"] == "vNIC":
                                vn = p.get("vnic", "vNIC")
                                v_desc = []
                                if p.get("operState"):
                                    v_desc.append(f"State: {p['operState']}")
                                if p.get("vethId"):
                                    v_desc.append(f"Veth: {p['vethId']}")
                                rl = p.get("ratelimit", "")
                                if rl:
                                    try:
                                        rl_val = int(rl)
                                        v_desc.append(f"Rate: {rl_val // 1000} Gbps" if rl_val >= 1000 else f"Rate: {rl_val} Mbps")
                                    except (ValueError, TypeError):
                                        pass
                                if p.get("pinned"):
                                    pinned_label = p.get("pinned", "").split("/")[-1] if "/" in p.get("pinned", "") else p.get("pinned", "")
                                    v_desc.append(f"Pinned: {pinned_label}")
                                pc_node["children"].append(_node(
                                    f"vNIC: {vn}", "vnic",
                                    description="\n".join(v_desc),
                                    extra={"colour": "#f472b6"},
                                ))
                            else:
                                vh = p.get("vhba", "vHBA")
                                v_desc = []
                                if p.get("operState"):
                                    v_desc.append(f"State: {p['operState']}")
                                if p.get("vfcId"):
                                    v_desc.append(f"Vfc: {p['vfcId']}")
                                pinned_fc_dn = p.get("pinned", "")
                                fc_label_for_vhba = fc_port_labels.get(pinned_fc_dn, "")
                                if fc_label_for_vhba:
                                    v_desc.append(f"Pinned: {fc_label_for_vhba}")
                                fc_vsan_val = fc_port_vsan_topo.get(pinned_fc_dn, "")
                                if fc_vsan_val:
                                    v_desc.append(f"VSAN: {fc_vsan_val}")
                                elif p.get("vsan"):
                                    v_desc.append(f"VSAN: {p['vsan']}")
                                pc_node["children"].append(_node(
                                    f"vHBA: {vh}", "vhba",
                                    description="\n".join(v_desc),
                                    extra={"colour": "#f43f5e"},
                                ))

                        if pc_vlans_str:
                            vlan_ids = _expand_vlan_string(pc_vlans_str)
                            pc_node["children"].append(_node(
                                f"VLANs ({len(vlan_ids)})", "vlan_list",
                                extra={"colour": "#3b82f6", "vlanIds": vlan_ids, "vlanRanges": pc_vlans_str},
                            ))

                        fi_children.append(pc_node)

                    fi_node = _node(fi_label, "fi",
                                    children=fi_children,
                                    extra={"colour": "#06b6d4"})
                    iom_node["children"].append(fi_node)
                    b_node["children"].append(iom_node)

                ch_node["children"].append(b_node)

            root["children"].append(ch_node)

        # Add System QoS section at the top level of topology
        qos_section = self._build_qos_section()
        if qos_section["children"]:
            root["children"].append(qos_section)

        return root
