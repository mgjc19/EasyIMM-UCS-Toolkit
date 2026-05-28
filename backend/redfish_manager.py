"""
Redfish workspace manager.
Manages server connections, resource configurations, Terraform file generation,
and terraform execution for C885A Redfish-based server automation.
"""

import asyncio
import json
import re
import os
from pathlib import Path
from typing import Optional

WORKSPACE = Path(__file__).resolve().parent.parent / "redfish-workspace"

REDFISH_SCHEMAS = {
    "bios": {
        "label": "BIOS Configuration",
        "description": "Cisco UCS C885A M8 BIOS tokens organized by category. Changes require a host reboot to take effect.",
        "resource_type": "redfish_bios",
        "fields": [
            {"name": "system_id", "label": "System ID", "type": "string", "default": "system"},
            {"name": "reboot_on_changes", "label": "Reboot Host on Changes", "type": "boolean", "default": True,
             "description": "Automatically reboot host after BIOS changes to activate new settings"},
            # ── I/O Parameters ──
            {"name": "pcie_link_speed", "label": "PCIe Link Speed Capability", "type": "select",
             "options": ["Auto", "GEN1", "GEN2", "GEN3", "GEN4", "GEN5"], "default": "Auto",
             "description": "Maximum PCI Express interface speed (GEN5 = 32 GT/s)"},
            {"name": "pcie_ten_bit_tag", "label": "PCIe 10-Bit Tag Support", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto",
             "description": "Extended tag field in PCIe transactions for improved routing"},
            {"name": "pcie_ari_support", "label": "PCIe ARI Support", "type": "select",
             "options": ["Auto", "Enable", "Disable"], "default": "Auto",
             "description": "Alternative Routing-ID Interpretation for efficient device addressing"},
            {"name": "sriov_support", "label": "SR-IOV Support", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Enabled",
             "description": "Single Root I/O Virtualization -- PCIe device appears as multiple physical devices"},
            {"name": "ipv4_pxe", "label": "IPv4 PXE Support", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Enabled"},
            {"name": "ipv6_pxe", "label": "IPv6 PXE Support", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Disabled"},
            {"name": "ipv4_http", "label": "IPv4 HTTP Boot Support", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Disabled"},
            {"name": "ipv6_http", "label": "IPv6 HTTP Boot Support", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Disabled"},
            # ── Server Management ──
            {"name": "frb2_timer", "label": "FRB-2 Timer", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Enabled",
             "description": "Fault Resilient Boot timer for POST recovery"},
            {"name": "console_redirection", "label": "Console Redirection", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Enabled",
             "description": "Serial port console redirection during POST and BIOS boot"},
            {"name": "terminal_type", "label": "Terminal Type", "type": "select",
             "options": ["PC-ANSI", "VT100", "VT100-PLUS", "VT-UTF8"], "default": "VT-UTF8"},
            {"name": "os_watchdog_timer", "label": "OS Watchdog Timer", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Disabled",
             "description": "Track OS boot time and take action if it exceeds timeout"},
            {"name": "os_wtd_timer_timeout", "label": "OS Watchdog Timer Timeout (min)", "type": "integer", "default": 10,
             "description": "Minutes before watchdog expires (1-30)"},
            {"name": "os_wtd_timer_policy", "label": "OS Watchdog Timer Policy", "type": "select",
             "options": ["Do Nothing", "Reset", "Power Down", "Power Cycle"], "default": "Reset"},
            {"name": "baud_rate", "label": "Serial Baud Rate (bps)", "type": "select",
             "options": ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"], "default": "115200"},
            {"name": "flow_control", "label": "Serial Flow Control", "type": "select",
             "options": ["None", "Hardware RTS/CTS"], "default": "None"},
            # ── Security ──
            {"name": "tpm_state", "label": "TPM State", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Enabled",
             "description": "Trusted Platform Module for cryptographic key storage and integrity checks"},
            {"name": "tpm_pending_operation", "label": "TPM Pending Operation", "type": "select",
             "options": ["None", "TpmClear"], "default": "None"},
            {"name": "security_device_support", "label": "Security Device Support", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Enabled"},
            {"name": "sha256_pcr_bank", "label": "SHA-256 PCR Bank", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Enabled"},
            {"name": "sha384_pcr_bank", "label": "SHA-384 PCR Bank", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Disabled"},
            {"name": "password_protection_runtime", "label": "Password Protection of Runtime Variables", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Disabled"},
            # ── Memory ──
            {"name": "iommu", "label": "IOMMU", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto",
             "description": "AMD I/O Memory Management Unit for virtual-to-physical address mapping"},
            {"name": "numa_nodes_per_socket", "label": "NUMA Nodes Per Socket", "type": "select",
             "options": ["Auto", "NPS0", "NPS1", "NPS2", "NPS4"], "default": "Auto",
             "description": "NPS0=1/system, NPS1=1/socket, NPS2=2/socket, NPS4=4/socket"},
            {"name": "tsme", "label": "TSME (Transparent Secure Memory Encryption)", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto"},
            {"name": "smee", "label": "SMEE (Secure Memory Encryption Enable)", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto"},
            {"name": "sev_snp_support", "label": "SEV-SNP Support", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto",
             "description": "AMD Secure Encrypted Virtualization -- Secure Nested Paging"},
            {"name": "chipselect_interleaving", "label": "Chipselect Interleaving", "type": "select",
             "options": ["Auto", "Disabled"], "default": "Auto"},
            {"name": "dram_refresh_rate", "label": "DRAM Refresh Rate", "type": "select",
             "options": ["3.9 usec", "1.95 usec"], "default": "3.9 usec"},
            {"name": "ddr_healing_bist", "label": "DDR Healing BIST", "type": "select",
             "options": ["Disabled", "PMU Mem BIST", "Self-Healing Mem BIST", "PMU and Self-Healing Mem BIST"], "default": "Disabled",
             "description": "DDR memory diagnostics and fault repair during boot"},
            {"name": "l1_burst_prefetch", "label": "L1 Burst Prefetch Mode", "type": "select",
             "options": ["Auto", "Enable", "Disable"], "default": "Auto"},
            {"name": "bme_dma_mitigation", "label": "BME DMA Mitigation", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Disabled",
             "description": "Disable PCI BME bit to mitigate unauthorized external DMA"},
            {"name": "dram_scrub_time", "label": "DRAM Scrub Time", "type": "select",
             "options": ["Auto", "Disabled", "1 hour", "4 hours", "8 hours", "16 hours", "24 hours", "48 hours"], "default": "Auto"},
            {"name": "dram_boot_ppr", "label": "DRAM Boot Time Post Package Repair", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Enabled"},
            {"name": "dram_runtime_ppr", "label": "DRAM Runtime Post Package Repair", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Enabled"},
            {"name": "bank_swap_mode", "label": "Bank Swap Mode", "type": "select",
             "options": ["Auto", "Disable", "Swap CPU"], "default": "Auto"},
            {"name": "memory_interleaving", "label": "Memory Interleaving", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto"},
            {"name": "above_4g_decoding", "label": "Above 4G MMIO Decoding", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Enabled",
             "description": "Map I/O of 64-bit PCI devices to 4GB+ address space"},
            {"name": "snp_memory_coverage", "label": "SNP Memory (RMP Table) Coverage", "type": "select",
             "options": ["Auto", "Enabled", "Disabled", "Custom"], "default": "Auto"},
            # ── Processor ──
            {"name": "svm_mode", "label": "SVM Mode (AMD Virtualization)", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Enabled",
             "description": "AMD Secure Virtual Machine Technology"},
            {"name": "smt_control", "label": "SMT Control (Hyperthreading)", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto",
             "description": "AMD Simultaneous MultiThreading -- parallel thread execution per core"},
            {"name": "avx512", "label": "AVX512", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto",
             "description": "Advanced Vector Extensions 512-bit instruction set"},
            {"name": "global_cstate_control", "label": "Global C-state Control", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto",
             "description": "AMD IO-based C-state generation and DF C-states"},
            {"name": "df_pstate_freq_optimizer", "label": "DF PState Frequency Optimizer", "type": "select",
             "options": ["Auto", "Enable", "Disable"], "default": "Auto",
             "description": "Optimize Data Fabric frequency states for performance/power balance"},
            {"name": "xgmi_force_link_width", "label": "xGMI Force Link Width", "type": "select",
             "options": ["Auto", "0", "1", "2"], "default": "Auto",
             "description": "Infinity Fabric interconnect link width (2=maximum bandwidth)"},
            {"name": "xgmi_max_speed", "label": "3-Link xGMI Max Speed", "type": "select",
             "options": ["Auto", "20Gbps", "25Gbps", "32Gbps"], "default": "Auto"},
            {"name": "downcore_mode", "label": "DownCore Mode", "type": "select",
             "options": ["Enablement Option", "Bitmap"], "default": "Enablement Option",
             "description": "Configure active processor cores for performance/power optimization"},
            {"name": "ccd_control", "label": "CCD Control", "type": "select",
             "options": ["Auto", "2 CCDs", "3 CCDs", "4 CCDs", "6 CCDs"], "default": "Auto",
             "description": "Number of Core Complex Dies enabled per socket"},
            {"name": "local_apic_mode", "label": "Local APIC Mode", "type": "select",
             "options": ["Auto", "XAPIC", "X2APIC"], "default": "Auto"},
            {"name": "streaming_stores", "label": "Streaming Stores Control", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto"},
            {"name": "acpi_srat_l3_numa", "label": "ACPI SRAT L3 Cache As NUMA Domain", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto",
             "description": "Declare each CCX as its own NUMA domain"},
            {"name": "apbdis", "label": "APBDIS (APB Disable to SMU)", "type": "select",
             "options": ["Auto", "0", "1"], "default": "Auto"},
            # ── Power / Performance ──
            {"name": "power_profile", "label": "Power Profile Selection", "type": "select",
             "options": ["High Performance Mode", "Efficiency Mode", "Maximum IO Performance Mode", "Balanced Memory Performance Mode"],
             "default": "High Performance Mode",
             "description": "Predefined power/performance profile"},
            {"name": "core_perf_boost", "label": "Core Performance Boost", "type": "select",
             "options": ["Auto", "Disabled"], "default": "Auto",
             "description": "AMD processor frequency boost on idle cores"},
            {"name": "cppc", "label": "CPPC (Collaborative Processor Performance Control)", "type": "select",
             "options": ["Auto", "Enable", "Disable"], "default": "Auto",
             "description": "OS-processor collaboration for performance and power management"},
            {"name": "determinism_enable", "label": "Determinism Enable", "type": "select",
             "options": ["Power", "Performance"], "default": "Performance",
             "description": "Power=energy-efficient consistency, Performance=max performance consistency"},
            {"name": "l1_stream_hw_prefetcher", "label": "L1 Stream HW Prefetcher", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto",
             "description": "Speculatively fetch data/instructions into L1 cache"},
            {"name": "l2_stream_hw_prefetcher", "label": "L2 Stream HW Prefetcher", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto",
             "description": "Speculatively fetch data/instructions into L2 cache"},
            {"name": "power_down_enable", "label": "Memory Power Down Enable", "type": "select",
             "options": ["Auto", "Enabled", "Disabled"], "default": "Auto",
             "description": "Allow RAM to enter low-power state when idle"},
            # ── Custom overrides (catch-all) ──
            {"name": "bios_attributes", "label": "Additional BIOS Attributes", "type": "map",
             "description": "Any extra BIOS token overrides not listed above (key = Redfish attribute name, value = desired value)"},
        ],
    },
    "bios_reset": {
        "label": "BIOS Reset to Defaults",
        "description": "Reset all BIOS settings to factory defaults. Use with caution on production servers.",
        "resource_type": "redfish_bios_reset",
        "fields": [
            {"name": "system_id", "label": "System ID", "type": "string", "default": "system"},
            {"name": "reset_bios_to_default", "label": "Reset BIOS to Default", "type": "boolean", "default": False},
        ],
    },
    "boot_order": {
        "label": "Boot Order",
        "description": "Configure UEFI boot order and boot devices. Supports drag-and-drop reordering.",
        "resource_type": "redfish_boot",
        "fields": [
            {"name": "system_id", "label": "System ID", "type": "string", "default": "system"},
            {"name": "reboot_on_changes", "label": "Reboot Host on Changes", "type": "boolean", "default": True},
            {"name": "uefi_secure_boot", "label": "UEFI Secure Boot", "type": "select",
             "options": ["Enabled", "Disabled"], "default": "Disabled",
             "description": "Verify EFI drivers, applications and OS are signed before execution. Supported on Ubuntu 22.04+, RHEL 9.4+, Rocky 9.5+"},
            {"name": "one_time_boot_device", "label": "One-Time Boot Device", "type": "select",
             "options": ["", "None", "Pxe", "Cd", "Usb", "Hdd", "BiosSetup", "UefiShell", "UefiHttp"], "default": "",
             "description": "Boot from this device once on next reboot only, then revert to normal boot order"},
            {"name": "boot_devices", "label": "Persistent Boot Order", "type": "boot_devices",
             "description": "Ordered list of boot devices. Each entry needs an alias (display name) and boot option ID (e.g. Boot0004). Use GET /redfish/v1/Systems/system/BootOptions to discover available IDs.",
             "default": []},
        ],
    },
    "power": {
        "label": "Power State",
        "description": "Control server power state via Redfish",
        "resource_type": "redfish_power",
        "fields": [
            {"name": "system_id", "label": "System ID", "type": "string", "default": "system"},
            {"name": "desired_power_state", "label": "Desired Power State", "type": "select",
             "options": ["on", "off", "GracefulShutdown", "ForceRestart", "GracefulRestart", "ForceOn", "ForceOff", "Nmi", "PushPowerButton"],
             "default": "on",
             "description": "on/off = set desired state. GracefulShutdown/ForceRestart = immediate actions."},
        ],
    },
    "identify_led": {
        "label": "Identify LED",
        "description": "Toggle the server locate/identify LED for physical identification in the rack",
        "resource_type": "redfish_identify_led",
        "fields": [
            {"name": "system_id", "label": "System ID", "type": "string", "default": "system"},
            {"name": "identify_led", "label": "LED Active", "type": "boolean", "default": False,
             "description": "Turn on the blue locator LED on the server chassis"},
        ],
    },
    "bmc_settings": {
        "label": "BMC Settings",
        "description": "Configure BMC (c885a manager) DNS, NTP, and domain settings",
        "resource_type": "redfish_bmc_settings",
        "fields": [
            {"name": "manager_id", "label": "Manager ID", "type": "string", "default": "c885a",
             "description": "Redfish Manager ID (c885a for C885A servers)"},
            {"name": "dns_interface_id", "label": "DNS Interface", "type": "string", "default": "eth0"},
            {"name": "dns_servers", "label": "DNS Servers", "type": "string_list", "default": ["8.8.8.8", "8.8.4.4"]},
            {"name": "ntp_servers", "label": "NTP Servers", "type": "string_list", "default": ["pool.ntp.org"]},
            {"name": "bmc_domain_name", "label": "Domain Name", "type": "string", "default": ""},
            {"name": "reset_bmc", "label": "Reset BMC After Changes", "type": "boolean", "default": False,
             "description": "Restart BMC manager services to apply changes. Takes 30-60s to recover."},
        ],
    },
    "bmc_network_protocol": {
        "label": "BMC Network Protocols",
        "description": "Configure BMC network protocol settings (SSH, HTTPS, IPMI, KVM, SNMP)",
        "resource_type": "redfish_bmc_network_protocol",
        "fields": [
            {"name": "ssh_enabled", "label": "SSH Enabled", "type": "boolean", "default": True},
            {"name": "ssh_port", "label": "SSH Port", "type": "integer", "default": 22},
            {"name": "https_enabled", "label": "HTTPS Enabled", "type": "boolean", "default": True},
            {"name": "https_port", "label": "HTTPS Port", "type": "integer", "default": 443},
            {"name": "ipmi_enabled", "label": "IPMI Over LAN Enabled", "type": "boolean", "default": False},
            {"name": "ipmi_port", "label": "IPMI Port", "type": "integer", "default": 623},
            {"name": "kvmip_enabled", "label": "KVM-IP Enabled", "type": "boolean", "default": True},
            {"name": "kvmip_port", "label": "KVM-IP Port", "type": "integer", "default": 2068},
            {"name": "snmp_enabled", "label": "SNMP Enabled", "type": "boolean", "default": False},
            {"name": "snmp_port", "label": "SNMP Port", "type": "integer", "default": 161},
        ],
    },
    "virtual_media": {
        "label": "Virtual Media",
        "description": "Mount ISO images via virtual media for OS installation or recovery",
        "resource_type": "redfish_virtual_media",
        "fields": [
            {"name": "mount_virtual_media", "label": "Mount Virtual Media", "type": "boolean", "default": False},
            {"name": "virtual_media_id", "label": "Media Slot", "type": "select",
             "options": ["CD0", "CD1", "RemoteMap0"], "default": "CD0"},
            {"name": "virtual_media_image_url", "label": "Image URL", "type": "string", "default": "",
             "description": "Full URL to the ISO image (e.g. https://fileserver.example.com/iso/ubuntu-22.04.iso)"},
            {"name": "virtual_media_transfer_protocol", "label": "Transfer Protocol", "type": "select",
             "options": ["HTTP", "HTTPS", "NFS", "CIFS"], "default": "HTTPS"},
            {"name": "virtual_media_write_protected", "label": "Write Protected", "type": "boolean", "default": True},
        ],
    },
    "secure_boot": {
        "label": "UEFI Secure Boot",
        "description": "Manage UEFI Secure Boot settings and key database. Supported on Ubuntu 22.04+, RHEL 9.4+, Rocky 9.5+",
        "resource_type": "redfish_secure_boot",
        "fields": [
            {"name": "secure_boot_enabled", "label": "Secure Boot Enabled", "type": "boolean", "default": False,
             "description": "When enabled, only signed EFI drivers and OS loaders are allowed to execute"},
            {"name": "secure_boot_mode", "label": "Secure Boot Mode", "type": "select",
             "options": ["SetupMode", "UserMode", "AuditMode", "DeployedMode"], "default": "DeployedMode",
             "description": "SetupMode=keys can be modified, UserMode=keys locked, DeployedMode=production"},
            {"name": "secure_boot_reset_keys_type", "label": "Reset Keys", "type": "select",
             "options": ["", "ResetAllKeysToDefault", "DeleteAllKeys"], "default": "",
             "description": "Reset secure boot key database to factory defaults or clear all keys"},
        ],
    },
    "event_subscription": {
        "label": "Event Subscription",
        "description": "Create Redfish event subscriptions (webhooks) for server alerts and notifications",
        "resource_type": "redfish_event_subscription",
        "fields": [
            {"name": "create_event_subscription", "label": "Create Subscription", "type": "boolean", "default": False},
            {"name": "event_subscription_destination", "label": "Destination URL", "type": "string", "default": "",
             "description": "HTTPS endpoint to receive Redfish events (e.g. https://monitoring.example.com/webhook)"},
            {"name": "event_subscription_protocol", "label": "Protocol", "type": "select",
             "options": ["Redfish", "SNMPv1", "SNMPv2c", "SNMPv3", "SMTP"], "default": "Redfish"},
            {"name": "event_subscription_context", "label": "Context", "type": "string", "default": "c885a-webhook",
             "description": "Identifier string sent with each event for correlation"},
            {"name": "event_subscription_types", "label": "Event Types", "type": "string_list",
             "default": ["Alert", "StatusChange"],
             "description": "Types: Alert, StatusChange, ResourceAdded, ResourceRemoved, ResourceUpdated"},
        ],
    },
    "log_service": {
        "label": "Log Service",
        "description": "Manage BMC event logs (view status, clear logs)",
        "resource_type": "redfish_log_service",
        "fields": [
            {"name": "clear_event_log", "label": "Clear Event Log", "type": "boolean", "default": False,
             "description": "Clear all entries from the BMC event log"},
            {"name": "log_service_id", "label": "Log Service ID", "type": "string", "default": "EventLog"},
        ],
    },
}


def _ensure_workspace():
    WORKSPACE.mkdir(parents=True, exist_ok=True)


def _config_path() -> Path:
    return WORKSPACE / "config.json"


def _load_config() -> dict:
    _ensure_workspace()
    path = _config_path()
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {
        "server": {
            "endpoint": "",
            "username": "admin",
            "password": "",
            "insecure": True,
        },
        "resources": {},
        "enabled": [],
    }


def _save_config(config: dict):
    _ensure_workspace()
    with open(_config_path(), "w") as f:
        json.dump(config, f, indent=2)


def get_schemas() -> dict:
    return REDFISH_SCHEMAS


def get_server_config() -> dict:
    cfg = _load_config()
    srv = cfg.get("server", {})
    return {
        "endpoint": srv.get("endpoint", ""),
        "username": srv.get("username", "admin"),
        "password": "****" if srv.get("password") else "",
        "insecure": srv.get("insecure", True),
        "has_password": bool(srv.get("password")),
    }


def save_server_config(endpoint: str, username: str, password: str, insecure: bool = True):
    cfg = _load_config()
    cfg["server"] = {
        "endpoint": endpoint,
        "username": username,
        "password": password,
        "insecure": insecure,
    }
    _save_config(cfg)


def get_resource_config(resource_key: str) -> dict:
    cfg = _load_config()
    schema = REDFISH_SCHEMAS.get(resource_key)
    if not schema:
        return {}
    defaults = {}
    for field in schema["fields"]:
        defaults[field["name"]] = field.get("default", "")
    saved = cfg.get("resources", {}).get(resource_key, {})
    merged = {**defaults, **saved}
    merged["_enabled"] = resource_key in cfg.get("enabled", [])
    return merged


def save_resource_config(resource_key: str, data: dict):
    cfg = _load_config()
    enabled = data.pop("_enabled", False)
    if "resources" not in cfg:
        cfg["resources"] = {}
    cfg["resources"][resource_key] = data
    if "enabled" not in cfg:
        cfg["enabled"] = []
    if enabled and resource_key not in cfg["enabled"]:
        cfg["enabled"].append(resource_key)
    elif not enabled and resource_key in cfg["enabled"]:
        cfg["enabled"].remove(resource_key)
    _save_config(cfg)


def get_all_resource_configs() -> dict:
    result = {}
    for key in REDFISH_SCHEMAS:
        result[key] = get_resource_config(key)
    return result


def _tf_value(val):
    """Format a Python value as HCL-compatible."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        items = ", ".join(f'"{v}"' for v in val)
        return f"[{items}]"
    if isinstance(val, dict):
        lines = []
        for k, v in val.items():
            lines.append(f'    {k} = "{v}"')
        return "{\n" + "\n".join(lines) + "\n  }"
    return f'"{val}"'


def generate_terraform_files():
    """Generate provider.tf, variables.tf, main.tf, and terraform.tfvars from config."""
    _ensure_workspace()
    cfg = _load_config()
    server = cfg.get("server", {})
    enabled = cfg.get("enabled", [])
    resources = cfg.get("resources", {})

    provider_tf = '''terraform {
  required_providers {
    redfish = {
      source = "cisco/redfish"
    }
  }
}

provider "redfish" {
  endpoint = var.bmc_endpoint
  username = var.bmc_username
  password = var.bmc_password
  insecure = var.bmc_insecure
}
'''

    variables_lines = [
        'variable "bmc_endpoint" {\n  type = string\n}\n',
        'variable "bmc_username" {\n  type = string\n}\n',
        'variable "bmc_password" {\n  type      = string\n  sensitive = true\n}\n',
        'variable "bmc_insecure" {\n  type    = bool\n  default = true\n}\n',
    ]

    main_lines = []
    tfvars_lines = [
        f'bmc_endpoint = "{server.get("endpoint", "")}"',
        f'bmc_username = "{server.get("username", "admin")}"',
        f'bmc_password = "{server.get("password", "")}"',
        f'bmc_insecure = {_tf_value(server.get("insecure", True))}',
        '',
    ]

    all_vars_declared = set()

    for res_key in enabled:
        schema = REDFISH_SCHEMAS.get(res_key)
        if not schema:
            continue
        data = resources.get(res_key, {})

        if res_key == "bios":
            merged_attrs = build_bios_attributes(data)
            for var_name in ("system_id", "reboot_on_changes", "bios_attributes"):
                if var_name in all_vars_declared:
                    continue
                all_vars_declared.add(var_name)
                if var_name == "bios_attributes":
                    variables_lines.append(
                        'variable "bios_attributes" {\n  type    = map(string)\n  default = '
                        + _tf_value(merged_attrs) + '\n}\n'
                    )
                    tfvars_lines.append(f'bios_attributes = {_tf_value(merged_attrs)}')
                elif var_name == "reboot_on_changes":
                    val = data.get("reboot_on_changes", True)
                    variables_lines.append(f'variable "reboot_on_changes" {{\n  type    = bool\n  default = {_tf_value(val)}\n}}\n')
                    tfvars_lines.append(f'reboot_on_changes = {_tf_value(val)}')
                else:
                    val = data.get("system_id", "system")
                    variables_lines.append(f'variable "system_id" {{\n  type    = string\n  default = {_tf_value(val)}\n}}\n')
                    tfvars_lines.append(f'system_id = {_tf_value(val)}')
            _generate_resource_block(schema, res_key, data, main_lines)
            continue

        for field in schema["fields"]:
            fname = field["name"]
            if fname in all_vars_declared:
                continue
            all_vars_declared.add(fname)

            ftype = field["type"]
            tf_type = "string"
            if ftype == "boolean":
                tf_type = "bool"
            elif ftype == "integer":
                tf_type = "number"
            elif ftype == "string_list":
                tf_type = "list(string)"
            elif ftype == "map":
                tf_type = "map(string)"
            elif ftype == "boot_devices":
                tf_type = 'list(object({ alias = string, id = string }))'

            default_val = data.get(fname, field.get("default", ""))
            variables_lines.append(
                f'variable "{fname}" {{\n  type    = {tf_type}\n  default = {_tf_value(default_val)}\n}}\n'
            )
            tfvars_lines.append(f'{fname} = {_tf_value(default_val)}')

        _generate_resource_block(schema, res_key, data, main_lines)

    files = ["provider.tf", "variables.tf", "main.tf", "terraform.tfvars"]
    (WORKSPACE / "provider.tf").write_text(provider_tf)
    (WORKSPACE / "variables.tf").write_text("\n".join(variables_lines))
    (WORKSPACE / "main.tf").write_text("\n".join(main_lines) if main_lines else "# No resources enabled\n")
    (WORKSPACE / "terraform.tfvars").write_text("\n".join(tfvars_lines))

    return {
        "ok": True,
        "enabled_resources": enabled,
        "files_written": [str(WORKSPACE / f) for f in files],
        "workspace": str(WORKSPACE),
    }


_BIOS_FIELD_TO_REDFISH_TOKEN = {
    "pcie_link_speed": "PcieLinkSpeedCapability",
    "pcie_ten_bit_tag": "PcieTenBitTagSupport",
    "pcie_ari_support": "PcieAriSupport",
    "sriov_support": "SriovSupport",
    "ipv4_pxe": "IPv4PxeSupport",
    "ipv6_pxe": "IPv6PxeSupport",
    "ipv4_http": "IPv4HttpSupport",
    "ipv6_http": "IPv6HttpSupport",
    "frb2_timer": "Frb2Timer",
    "console_redirection": "ConsoleRedirection",
    "terminal_type": "TerminalType",
    "os_watchdog_timer": "OsWatchdogTimer",
    "os_wtd_timer_timeout": "OsWtdTimerTimeout",
    "os_wtd_timer_policy": "OsWtdTimerPolicy",
    "baud_rate": "BitsPerSecond",
    "flow_control": "FlowControl",
    "tpm_state": "TpmState",
    "tpm_pending_operation": "TpmPendingOperation",
    "security_device_support": "SecurityDeviceSupport",
    "sha256_pcr_bank": "Sha256PcrBank",
    "sha384_pcr_bank": "Sha384PcrBank",
    "password_protection_runtime": "PasswordProtectionRuntimeVariables",
    "iommu": "IOMMU",
    "numa_nodes_per_socket": "NumaNodesPerSocket",
    "tsme": "TSME",
    "smee": "SMEE",
    "sev_snp_support": "SevSnpSupport",
    "chipselect_interleaving": "ChipselectInterleaving",
    "dram_refresh_rate": "DramRefreshRate",
    "ddr_healing_bist": "DdrHealingBist",
    "l1_burst_prefetch": "L1BurstPrefetchMode",
    "bme_dma_mitigation": "BmeDmaMitigation",
    "dram_scrub_time": "DramScrubTime",
    "dram_boot_ppr": "DramBootTimePpr",
    "dram_runtime_ppr": "DramRuntimePpr",
    "bank_swap_mode": "BankSwapMode",
    "memory_interleaving": "MemoryInterleaving",
    "above_4g_decoding": "Above4GDecoding",
    "snp_memory_coverage": "SnpMemoryCoverage",
    "svm_mode": "SvmMode",
    "smt_control": "SmtControl",
    "avx512": "Avx512",
    "global_cstate_control": "GlobalCstateControl",
    "df_pstate_freq_optimizer": "DfPstateFrequencyOptimizer",
    "xgmi_force_link_width": "XgmiForceWidth",
    "xgmi_max_speed": "XgmiMaxSpeed",
    "downcore_mode": "DownCoreMode",
    "ccd_control": "CcdControl",
    "local_apic_mode": "LocalApicMode",
    "streaming_stores": "StreamingStoresControl",
    "acpi_srat_l3_numa": "AcpiSratL3CacheAsNumaDomain",
    "apbdis": "Apbdis",
    "power_profile": "PowerProfileSelection",
    "core_perf_boost": "CorePerformanceBoost",
    "cppc": "Cppc",
    "determinism_enable": "DeterminismEnable",
    "l1_stream_hw_prefetcher": "L1StreamHwPrefetcher",
    "l2_stream_hw_prefetcher": "L2StreamHwPrefetcher",
    "power_down_enable": "PowerDownEnable",
}


def build_bios_attributes(data: dict) -> dict:
    """Merge structured BIOS fields and the catch-all map into a single Redfish attributes dict."""
    attrs = {}
    skip = {"system_id", "reboot_on_changes", "bios_attributes", "_enabled"}
    for field_name, value in data.items():
        if field_name in skip or value is None:
            continue
        token = _BIOS_FIELD_TO_REDFISH_TOKEN.get(field_name)
        if token:
            schema_field = next((f for f in REDFISH_SCHEMAS["bios"]["fields"] if f["name"] == field_name), None)
            default = schema_field.get("default", "") if schema_field else ""
            if str(value) != str(default):
                attrs[token] = str(value) if not isinstance(value, str) else value
    extras = data.get("bios_attributes")
    if isinstance(extras, dict):
        attrs.update(extras)
    return attrs


def _generate_resource_block(schema: dict, res_key: str, data: dict, lines: list):
    """Append an HCL resource block for the given resource type."""
    rt = schema["resource_type"]

    if res_key == "bios":
        lines.append(f'''resource "{rt}" "managed" {{
  count             = length(var.bios_attributes) > 0 ? 1 : 0
  system_id         = var.system_id
  bios_attributes   = var.bios_attributes
  reboot_on_changes = var.reboot_on_changes
}}
''')
    elif res_key == "bios_reset":
        lines.append(f'''resource "{rt}" "managed" {{
  count     = var.reset_bios_to_default ? 1 : 0
  system_id = var.system_id
}}
''')
    elif res_key == "boot_order":
        lines.append(f'''resource "{rt}" "managed" {{
  system_id         = var.system_id
  boot_target       = join(", ", [for d in var.boot_devices : d.alias])
  boot_order        = [for d in var.boot_devices : d.id]
  reboot_on_changes = var.reboot_on_changes
}}
''')
    elif res_key == "power":
        lines.append(f'''resource "{rt}" "managed" {{
  system_id     = var.system_id
  desired_state = var.desired_power_state
}}
''')
    elif res_key == "identify_led":
        lines.append(f'''resource "{rt}" "managed" {{
  system_id = var.system_id
  active    = var.identify_led
}}
''')
    elif res_key == "bmc_settings":
        lines.append(f'''resource "{rt}" "managed" {{
  manager_id       = var.manager_id
  dns_interface_id = var.dns_interface_id
  dns_servers      = var.dns_servers
  ntp_servers      = var.ntp_servers
  domain_name      = var.bmc_domain_name
  reset_bmc        = var.reset_bmc
}}
''')
    elif res_key == "bmc_network_protocol":
        lines.append(f'''resource "{rt}" "managed" {{
  ssh_enabled   = var.ssh_enabled
  ssh_port      = var.ssh_port
  https_enabled = var.https_enabled
  https_port    = var.https_port
  ipmi_enabled  = var.ipmi_enabled
  ipmi_port     = var.ipmi_port
  kvmip_enabled = var.kvmip_enabled
  kvmip_port    = var.kvmip_port
  snmp_enabled  = var.snmp_enabled
  snmp_port     = var.snmp_port
}}
''')
    elif res_key == "virtual_media":
        lines.append(f'''resource "{rt}" "managed" {{
  count             = var.mount_virtual_media ? 1 : 0
  media_id          = var.virtual_media_id
  image_url         = var.virtual_media_image_url
  transfer_protocol = var.virtual_media_transfer_protocol
  write_protected   = var.virtual_media_write_protected
}}
''')
    elif res_key == "secure_boot":
        lines.append(f'''resource "{rt}" "managed" {{
  enabled         = var.secure_boot_enabled
  mode            = var.secure_boot_mode
  reset_keys_type = var.secure_boot_reset_keys_type
}}
''')
    elif res_key == "event_subscription":
        lines.append(f'''resource "{rt}" "managed" {{
  count       = var.create_event_subscription ? 1 : 0
  destination = var.event_subscription_destination
  protocol    = var.event_subscription_protocol
  context     = var.event_subscription_context
  event_types = var.event_subscription_types
}}
''')
    elif res_key == "log_service":
        lines.append(f'''resource "{rt}" "managed" {{
  count  = var.clear_event_log ? 1 : 0
  log_id = var.log_service_id
}}
''')


ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


async def run_terraform(action: str, callback=None) -> dict:
    """Run a terraform command in the Redfish workspace."""
    generate_terraform_files()

    cmd_map = {
        "init": ["terraform", "init", "-no-color"],
        "validate": ["terraform", "validate", "-no-color"],
        "plan": ["terraform", "plan", "-no-color"],
        "apply": ["terraform", "apply", "-auto-approve", "-no-color"],
        "destroy": ["terraform", "destroy", "-auto-approve", "-no-color"],
        "state_list": ["terraform", "state", "list"],
    }

    cmd = cmd_map.get(action)
    if not cmd:
        return {"success": False, "output": f"Unknown action: {action}", "exit_code": 1}

    env = {**os.environ}

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(WORKSPACE),
            env=env,
        )

        output_lines = []
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = ANSI_RE.sub("", line.decode("utf-8", errors="replace"))
            output_lines.append(text)
            if callback:
                await callback(text)

        await proc.wait()
        return {
            "success": proc.returncode == 0,
            "output": "".join(output_lines),
            "exit_code": proc.returncode,
        }
    except FileNotFoundError:
        msg = "terraform command not found. Is Terraform installed?"
        if callback:
            await callback(msg)
        return {"success": False, "output": msg, "exit_code": 127}
