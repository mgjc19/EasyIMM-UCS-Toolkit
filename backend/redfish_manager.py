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
        "label": "BIOS Attributes",
        "description": "Manage BIOS attributes on a Redfish-managed server",
        "resource_type": "redfish_bios",
        "fields": [
            {"name": "system_id", "label": "System ID", "type": "string", "default": "system"},
            {"name": "wrapper_key", "label": "Wrapper Key", "type": "string", "default": "Attributes"},
            {"name": "reboot_on_changes", "label": "Reboot on Changes", "type": "boolean", "default": True},
            {"name": "bios_attributes", "label": "BIOS Attributes", "type": "map",
             "description": "Key-value pairs of BIOS attribute names and their desired values (e.g. CbsCmnMemContextRestoreDdr = Enabled)"},
        ],
    },
    "bios_reset": {
        "label": "BIOS Reset to Defaults",
        "description": "Reset BIOS settings to factory defaults. Use with caution on production servers.",
        "resource_type": "redfish_bios_reset",
        "fields": [
            {"name": "system_id", "label": "System ID", "type": "string", "default": "system"},
            {"name": "reset_bios_to_default", "label": "Reset BIOS to Default", "type": "boolean", "default": False},
        ],
    },
    "boot_order": {
        "label": "Boot Order",
        "description": "Configure boot order and boot devices",
        "resource_type": "redfish_boot",
        "fields": [
            {"name": "system_id", "label": "System ID", "type": "string", "default": "system"},
            {"name": "reboot_on_changes", "label": "Reboot on Changes", "type": "boolean", "default": True},
            {"name": "boot_devices", "label": "Boot Devices", "type": "boot_devices",
             "description": "Ordered list of boot devices. Each entry needs an alias (display name) and ID (e.g. Boot0004)",
             "default": []},
        ],
    },
    "power": {
        "label": "Power State",
        "description": "Control server power state",
        "resource_type": "redfish_power",
        "fields": [
            {"name": "system_id", "label": "System ID", "type": "string", "default": "system"},
            {"name": "desired_power_state", "label": "Desired Power State", "type": "select",
             "options": ["on", "off", "GracefulShutdown", "ForceRestart", "GracefulRestart"],
             "default": "on"},
        ],
    },
    "identify_led": {
        "label": "Identify LED",
        "description": "Toggle the server locate/identify LED for physical identification",
        "resource_type": "redfish_identify_led",
        "fields": [
            {"name": "system_id", "label": "System ID", "type": "string", "default": "system"},
            {"name": "identify_led", "label": "LED Active", "type": "boolean", "default": False},
        ],
    },
    "bmc_settings": {
        "label": "BMC Settings",
        "description": "Configure BMC DNS, NTP, and domain settings",
        "resource_type": "redfish_bmc_settings",
        "fields": [
            {"name": "manager_id", "label": "Manager ID", "type": "string", "default": "bmc"},
            {"name": "dns_interface_id", "label": "DNS Interface", "type": "string", "default": "eth0"},
            {"name": "dns_servers", "label": "DNS Servers", "type": "string_list", "default": ["8.8.8.8", "8.8.4.4"]},
            {"name": "ntp_servers", "label": "NTP Servers", "type": "string_list", "default": ["pool.ntp.org"]},
            {"name": "bmc_domain_name", "label": "Domain Name", "type": "string", "default": ""},
            {"name": "reset_bmc", "label": "Reset BMC", "type": "boolean", "default": False,
             "description": "Restart BMC manager services. Takes 30-60s to recover."},
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
            {"name": "ipmi_enabled", "label": "IPMI Enabled", "type": "boolean", "default": False},
            {"name": "ipmi_port", "label": "IPMI Port", "type": "integer", "default": 623},
            {"name": "kvmip_enabled", "label": "KVM-IP Enabled", "type": "boolean", "default": True},
            {"name": "kvmip_port", "label": "KVM-IP Port", "type": "integer", "default": 2068},
            {"name": "snmp_enabled", "label": "SNMP Enabled", "type": "boolean", "default": False},
            {"name": "snmp_port", "label": "SNMP Port", "type": "integer", "default": 161},
        ],
    },
    "virtual_media": {
        "label": "Virtual Media",
        "description": "Mount ISO images via virtual media for OS installation",
        "resource_type": "redfish_virtual_media",
        "fields": [
            {"name": "mount_virtual_media", "label": "Mount Virtual Media", "type": "boolean", "default": False},
            {"name": "virtual_media_id", "label": "Media ID", "type": "string", "default": "CD0"},
            {"name": "virtual_media_image_url", "label": "Image URL", "type": "string", "default": "",
             "description": "HTTP/HTTPS/NFS URL to the ISO image"},
            {"name": "virtual_media_transfer_protocol", "label": "Transfer Protocol", "type": "select",
             "options": ["HTTP", "HTTPS", "NFS", "CIFS"], "default": "HTTP"},
            {"name": "virtual_media_write_protected", "label": "Write Protected", "type": "boolean", "default": True},
        ],
    },
    "secure_boot": {
        "label": "Secure Boot",
        "description": "Enable/disable UEFI Secure Boot",
        "resource_type": "redfish_secure_boot",
        "fields": [
            {"name": "secure_boot_enabled", "label": "Secure Boot Enabled", "type": "boolean", "default": False},
            {"name": "secure_boot_mode", "label": "Secure Boot Mode", "type": "select",
             "options": ["SetupMode", "UserMode", "AuditMode", "DeployedMode"], "default": "DeployedMode"},
            {"name": "secure_boot_reset_keys_type", "label": "Reset Keys Type", "type": "select",
             "options": ["", "ResetAllKeysToDefault", "DeleteAllKeys"], "default": ""},
        ],
    },
    "event_subscription": {
        "label": "Event Subscription",
        "description": "Create Redfish event subscriptions (webhooks) for alerts",
        "resource_type": "redfish_event_subscription",
        "fields": [
            {"name": "create_event_subscription", "label": "Create Subscription", "type": "boolean", "default": False},
            {"name": "event_subscription_destination", "label": "Destination URL", "type": "string", "default": "",
             "description": "HTTPS endpoint to receive Redfish events"},
            {"name": "event_subscription_protocol", "label": "Protocol", "type": "select",
             "options": ["Redfish", "SNMPv1", "SNMPv2c", "SNMPv3", "SMTP"], "default": "Redfish"},
            {"name": "event_subscription_context", "label": "Context", "type": "string", "default": "c885a-webhook"},
            {"name": "event_subscription_types", "label": "Event Types", "type": "string_list",
             "default": ["Alert", "StatusChange"]},
        ],
    },
    "log_service": {
        "label": "Log Service",
        "description": "Clear event logs on the server BMC",
        "resource_type": "redfish_log_service",
        "fields": [
            {"name": "clear_event_log", "label": "Clear Event Log", "type": "boolean", "default": False},
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

    (WORKSPACE / "provider.tf").write_text(provider_tf)
    (WORKSPACE / "variables.tf").write_text("\n".join(variables_lines))
    (WORKSPACE / "main.tf").write_text("\n".join(main_lines) if main_lines else "# No resources enabled\n")
    (WORKSPACE / "terraform.tfvars").write_text("\n".join(tfvars_lines))

    return {"ok": True, "enabled": enabled, "workspace": str(WORKSPACE)}


def _generate_resource_block(schema: dict, res_key: str, data: dict, lines: list):
    """Append an HCL resource block for the given resource type."""
    rt = schema["resource_type"]

    if res_key == "bios":
        lines.append(f'''resource "{rt}" "managed" {{
  count             = length(var.bios_attributes) > 0 ? 1 : 0
  system_id         = var.system_id
  wrapper_key       = var.wrapper_key
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
