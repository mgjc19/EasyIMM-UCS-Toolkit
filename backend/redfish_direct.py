"""
Direct Redfish API push -- bypasses Terraform and calls the BMC Redfish
endpoints directly using HTTP requests.
"""

import json
import urllib3
from typing import Optional

import requests

from redfish_manager import (
    _load_config,
    REDFISH_SCHEMAS,
    build_bios_attributes,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _session(endpoint: str, username: str, password: str, insecure: bool):
    """Create an authenticated requests.Session against the BMC."""
    s = requests.Session()
    s.auth = (username, password)
    s.verify = not insecure
    s.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    s.base_url = endpoint.rstrip("/")
    return s


def _url(session, path: str) -> str:
    return f"{session.base_url}{path}"


def _get(session, path: str) -> dict:
    r = session.get(_url(session, path), timeout=30)
    r.raise_for_status()
    return r.json()


def _patch(session, path: str, payload: dict) -> dict:
    r = session.patch(_url(session, path), json=payload, timeout=30)
    if r.status_code >= 400:
        detail = ""
        try:
            detail = json.dumps(r.json(), indent=2)
        except Exception:
            detail = r.text[:500]
        return {"ok": False, "status": r.status_code, "detail": detail}
    return {"ok": True, "status": r.status_code}


def _post(session, path: str, payload: dict) -> dict:
    r = session.post(_url(session, path), json=payload, timeout=30)
    if r.status_code >= 400:
        detail = ""
        try:
            detail = json.dumps(r.json(), indent=2)
        except Exception:
            detail = r.text[:500]
        return {"ok": False, "status": r.status_code, "detail": detail}
    return {"ok": True, "status": r.status_code}


def _safe_get(session, path: str) -> dict | None:
    """GET that returns None on error instead of raising."""
    try:
        return _get(session, path)
    except Exception:
        return None


def read_live_state() -> dict:
    """Read the current live configuration from the BMC for all resource types."""
    cfg = _load_config()
    server = cfg.get("server", {})
    endpoint = server.get("endpoint", "")
    username = server.get("username", "")
    password = server.get("password", "")
    insecure = server.get("insecure", True)

    if not endpoint or not username or not password:
        return {"ok": False, "error": "BMC connection not configured."}

    session = _session(endpoint, username, password, insecure)
    results = {}

    try:
        sys_data = _safe_get(session, "/redfish/v1/Systems/system")
    except Exception:
        return {"ok": False, "error": f"Cannot connect to BMC at {endpoint}"}

    if not sys_data:
        return {"ok": False, "error": f"Cannot connect to BMC at {endpoint}"}

    # ── BIOS ──
    try:
        bios_pending = _safe_get(session, "/redfish/v1/Systems/system/Bios/Settings")
        bios_current = _safe_get(session, "/redfish/v1/Systems/system/Bios")
        attrs = {}
        if bios_current:
            attrs = bios_current.get("Attributes", {})
        if bios_pending:
            attrs.update(bios_pending.get("Attributes", {}))
        if attrs:
            from redfish_manager import _BIOS_FIELD_TO_REDFISH_TOKEN
            reverse_map = {v: k for k, v in _BIOS_FIELD_TO_REDFISH_TOKEN.items()}
            bios_vals = {}
            extra_attrs = {}
            for token, val in attrs.items():
                field_name = reverse_map.get(token)
                if field_name:
                    bios_vals[field_name] = val
                else:
                    extra_attrs[token] = str(val)
            if extra_attrs:
                bios_vals["bios_attributes"] = extra_attrs
            results["bios"] = bios_vals
    except Exception:
        pass

    # ── Boot Order ──
    try:
        boot = sys_data.get("Boot", {})
        boot_vals = {}
        boot_order_ids = boot.get("BootOrder", [])
        if boot_order_ids:
            devices = []
            for bid in boot_order_ids:
                opt = _safe_get(session, f"/redfish/v1/Systems/system/BootOptions/{bid}")
                alias = opt.get("DisplayName", opt.get("Name", bid)) if opt else bid
                devices.append({"alias": alias, "id": bid})
            boot_vals["boot_devices"] = devices
        sb = boot.get("UefiTargetBootSourceOverride")
        if boot.get("BootSourceOverrideTarget"):
            boot_vals["one_time_boot_device"] = boot["BootSourceOverrideTarget"]
        results["boot_order"] = boot_vals
    except Exception:
        pass

    # ── Power State ──
    try:
        ps = sys_data.get("PowerState", "")
        state_map = {"On": "on", "Off": "off", "PoweringOn": "on", "PoweringOff": "off"}
        results["power"] = {"desired_power_state": state_map.get(ps, ps.lower() if ps else "on")}
    except Exception:
        pass

    # ── Identify LED ──
    try:
        led = sys_data.get("IndicatorLED", "")
        results["identify_led"] = {"identify_led": led in ("Lit", "Blinking")}
    except Exception:
        pass

    # ── Secure Boot ──
    try:
        sb = _safe_get(session, "/redfish/v1/Systems/system/SecureBoot")
        if sb:
            results["secure_boot"] = {
                "secure_boot_enabled": sb.get("SecureBootEnable", False),
                "secure_boot_mode": sb.get("SecureBootMode", "DeployedMode"),
            }
    except Exception:
        pass

    # ── BMC Settings & Network Protocol ──
    try:
        mgr = _safe_get(session, "/redfish/v1/Managers/c885a")
        np = _safe_get(session, "/redfish/v1/Managers/c885a/NetworkProtocol")
        bmc_vals = {}
        if np:
            ntp = np.get("NTP", {})
            bmc_vals["ntp_servers"] = ntp.get("NTPServers", [])
        results["bmc_settings"] = bmc_vals

        if np:
            proto_vals = {}
            for proto, key in [("SSH", "ssh"), ("HTTPS", "https"), ("IPMI", "ipmi"),
                               ("KVMIP", "kvmip"), ("SNMP", "snmp")]:
                p = np.get(proto, {})
                if p:
                    proto_vals[f"{key}_enabled"] = p.get("ProtocolEnabled", False)
                    proto_vals[f"{key}_port"] = p.get("Port", 0)
            results["bmc_network_protocol"] = proto_vals
    except Exception:
        pass

    # ── BMC Ethernet ──
    try:
        eth = _safe_get(session, "/redfish/v1/Managers/c885a/EthernetInterfaces/eth0")
        if eth:
            eth_vals = {
                "hostname": eth.get("HostName", ""),
                "fqdn": eth.get("FQDN", ""),
            }
            dhcp = eth.get("DHCPv4", {})
            eth_vals["ipv4_dhcp_enabled"] = dhcp.get("DHCPEnabled", True)
            ipv4s = eth.get("IPv4Addresses", [])
            if ipv4s:
                eth_vals["ipv4_address"] = ipv4s[0].get("Address", "")
                eth_vals["ipv4_subnet_mask"] = ipv4s[0].get("SubnetMask", "")
                eth_vals["ipv4_gateway"] = ipv4s[0].get("Gateway", "")
            vlan = eth.get("VLAN", {})
            eth_vals["vlan_enabled"] = vlan.get("VLANEnable", False)
            eth_vals["vlan_id"] = vlan.get("VLANId", 0)
            eth_vals["dns_servers"] = eth.get("NameServers", [])
            results["bmc_ethernet"] = eth_vals
    except Exception:
        pass

    # ── User Accounts ──
    try:
        accts_col = _safe_get(session, "/redfish/v1/AccountService/Accounts")
        if accts_col:
            members = accts_col.get("Members", [])
            for m in members[:1]:
                acct = _safe_get(session, m.get("@odata.id", ""))
                if acct and acct.get("UserName"):
                    results["user_accounts"] = {
                        "account_id": int(acct.get("Id", 1)),
                        "username": acct.get("UserName", ""),
                        "role_id": acct.get("RoleId", "ReadOnly"),
                        "account_enabled": acct.get("Enabled", True),
                    }
                    break
    except Exception:
        pass

    # ── Account Service ──
    try:
        asvc = _safe_get(session, "/redfish/v1/AccountService")
        if asvc:
            results["account_service"] = {
                "account_lockout_threshold": asvc.get("AccountLockoutThreshold", 5),
                "account_lockout_duration": asvc.get("AccountLockoutDuration", 300),
                "account_lockout_counter_reset": asvc.get("AccountLockoutCounterResetAfter", 300),
                "min_password_length": asvc.get("MinPasswordLength", 8),
            }
    except Exception:
        pass

    # ── Session Service ──
    try:
        ss = _safe_get(session, "/redfish/v1/SessionService")
        if ss:
            results["session_service"] = {
                "session_timeout": ss.get("SessionTimeout", 1800),
                "service_enabled": ss.get("ServiceEnabled", True),
            }
    except Exception:
        pass

    # ── Chassis Power ──
    try:
        pwr = _safe_get(session, "/redfish/v1/Chassis/1/Power")
        if pwr:
            pwr_vals = {}
            pc = pwr.get("PowerControl", [])
            if pc:
                limit = pc[0].get("PowerLimit", {})
                watts = limit.get("LimitInWatts")
                if watts and watts > 0:
                    pwr_vals["power_limit_enabled"] = True
                    pwr_vals["power_limit_watts"] = watts
                    pwr_vals["power_limit_exception"] = limit.get("LimitException", "NoAction")
                consumed = pc[0].get("PowerConsumedWatts")
                if consumed is not None:
                    pwr_vals["_current_watts"] = consumed
            results["chassis_power"] = pwr_vals
    except Exception:
        pass

    # ── Chassis Thermal (read-only sensor data) ──
    try:
        thermal = _safe_get(session, "/redfish/v1/Chassis/1/Thermal")
        if thermal:
            temps = []
            for t in thermal.get("Temperatures", [])[:10]:
                temps.append({
                    "name": t.get("Name", ""),
                    "reading_celsius": t.get("ReadingCelsius"),
                    "status": t.get("Status", {}).get("Health", ""),
                })
            fans = []
            for f in thermal.get("Fans", [])[:10]:
                fans.append({
                    "name": f.get("Name", ""),
                    "reading_rpm": f.get("Reading"),
                    "status": f.get("Status", {}).get("Health", ""),
                })
            results["chassis_thermal"] = {"_temperatures": temps, "_fans": fans}
    except Exception:
        pass

    # ── Storage ──
    try:
        storage_col = _safe_get(session, "/redfish/v1/Systems/system/Storage")
        if storage_col:
            controllers = []
            for m in storage_col.get("Members", []):
                ctrl = _safe_get(session, m.get("@odata.id", ""))
                if ctrl:
                    controllers.append({
                        "id": ctrl.get("Id", ""),
                        "name": ctrl.get("Name", ""),
                        "drives": len(ctrl.get("Drives", [])),
                        "volumes": len((ctrl.get("Volumes", {}) or {}).get("Members", []) if isinstance(ctrl.get("Volumes"), dict) else []),
                    })
            results["storage"] = {"_controllers": controllers}
    except Exception:
        pass

    # ── Firmware Inventory ──
    try:
        fw_col = _safe_get(session, "/redfish/v1/UpdateService/FirmwareInventory")
        if fw_col:
            components = []
            for m in fw_col.get("Members", []):
                fw = _safe_get(session, m.get("@odata.id", ""))
                if fw:
                    components.append({
                        "id": fw.get("Id", ""),
                        "name": fw.get("Name", ""),
                        "version": fw.get("Version", ""),
                        "updateable": fw.get("Updateable", False),
                    })
            results["firmware_update"] = {"_inventory": components}
    except Exception:
        pass

    # ── System Inventory ──
    try:
        inv = {}
        inv["model"] = sys_data.get("Model", "")
        inv["manufacturer"] = sys_data.get("Manufacturer", "")
        inv["serial_number"] = sys_data.get("SerialNumber", "")
        inv["bios_version"] = sys_data.get("BiosVersion", "")
        inv["total_memory_gb"] = sys_data.get("MemorySummary", {}).get("TotalSystemMemoryGiB", 0)
        inv["processor_count"] = sys_data.get("ProcessorSummary", {}).get("Count", 0)
        inv["processor_model"] = sys_data.get("ProcessorSummary", {}).get("Model", "")
        inv["power_state"] = sys_data.get("PowerState", "")
        inv["health"] = sys_data.get("Status", {}).get("Health", "")
        results["system_inventory"] = inv
    except Exception:
        pass

    # ── Virtual Media ──
    try:
        vm_col = _safe_get(session, "/redfish/v1/Managers/c885a/VirtualMedia")
        if vm_col:
            for m in vm_col.get("Members", []):
                vm = _safe_get(session, m.get("@odata.id", ""))
                if vm and vm.get("Image"):
                    results["virtual_media"] = {
                        "mount_virtual_media": True,
                        "virtual_media_id": vm.get("Id", "CD0"),
                        "virtual_media_image_url": vm.get("Image", ""),
                        "virtual_media_write_protected": vm.get("WriteProtected", True),
                    }
                    break
    except Exception:
        pass

    # ── NTP ──
    try:
        np = _safe_get(session, "/redfish/v1/Managers/c885a/NetworkProtocol")
        if np:
            ntp_data = np.get("NTP", {})
            servers = ntp_data.get("NTPServers", [])
            ntp_vals = {
                "ntp_enabled": ntp_data.get("ProtocolEnabled", False),
            }
            for i, s in enumerate(servers[:4]):
                ntp_vals[f"ntp_server_{i+1}"] = s or ""
            results["ntp_settings"] = ntp_vals
    except Exception:
        pass

    return {"ok": True, "live_state": results}


def push_all_enabled() -> dict:
    """Push all enabled resource configs directly to the BMC via Redfish API."""
    cfg = _load_config()
    server = cfg.get("server", {})
    endpoint = server.get("endpoint", "")
    username = server.get("username", "")
    password = server.get("password", "")
    insecure = server.get("insecure", True)

    if not endpoint or not username or not password:
        return {
            "ok": False,
            "results": [],
            "error": "BMC connection not configured. Save your server connection first.",
        }

    enabled = cfg.get("enabled", [])
    resources = cfg.get("resources", {})

    if not enabled:
        return {"ok": True, "results": [], "message": "No resources are enabled."}

    session = _session(endpoint, username, password, insecure)
    results = []

    for res_key in enabled:
        data = resources.get(res_key, {})
        schema = REDFISH_SCHEMAS.get(res_key)
        if not schema:
            continue
        try:
            result = _push_resource(session, res_key, data)
            results.append({"resource": res_key, "label": schema["label"], **result})
        except requests.exceptions.ConnectionError:
            results.append({
                "resource": res_key,
                "label": schema["label"],
                "ok": False,
                "detail": f"Connection failed to {endpoint}",
            })
        except Exception as e:
            results.append({
                "resource": res_key,
                "label": schema["label"],
                "ok": False,
                "detail": str(e),
            })

    all_ok = all(r.get("ok") for r in results)
    return {"ok": all_ok, "results": results}


def push_single(resource_key: str) -> dict:
    """Push a single resource config directly to the BMC."""
    cfg = _load_config()
    server = cfg.get("server", {})
    endpoint = server.get("endpoint", "")
    username = server.get("username", "")
    password = server.get("password", "")
    insecure = server.get("insecure", True)

    if not endpoint or not username or not password:
        return {"ok": False, "detail": "BMC connection not configured."}

    data = cfg.get("resources", {}).get(resource_key, {})
    schema = REDFISH_SCHEMAS.get(resource_key)
    if not schema:
        return {"ok": False, "detail": f"Unknown resource: {resource_key}"}

    session = _session(endpoint, username, password, insecure)
    try:
        return _push_resource(session, resource_key, data)
    except requests.exceptions.ConnectionError:
        return {"ok": False, "detail": f"Connection failed to {endpoint}"}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


def _push_resource(session, res_key: str, data: dict) -> dict:
    """Dispatch a single resource push to the correct Redfish endpoint."""
    system_id = data.get("system_id", "system")

    if res_key == "bios":
        attrs = build_bios_attributes(data)
        if not attrs:
            return {"ok": True, "detail": "No BIOS attributes to change", "skipped": True}
        return _patch(session, f"/redfish/v1/Systems/{system_id}/Bios/Settings",
                       {"Attributes": attrs})

    if res_key == "boot_order":
        payload = {}
        uefi_sb = data.get("uefi_secure_boot")
        if uefi_sb:
            payload["Boot"] = {"UefiSecureBoot": uefi_sb == "Enabled"}
        otbd = data.get("one_time_boot_device")
        if otbd:
            payload.setdefault("Boot", {})["BootSourceOverrideTarget"] = otbd
            payload["Boot"]["BootSourceOverrideEnabled"] = "Once"
        devices = data.get("boot_devices", [])
        if devices:
            boot_order = [d.get("id") for d in devices if d.get("id")]
            if boot_order:
                payload.setdefault("Boot", {})["BootOrder"] = boot_order
        if not payload:
            return {"ok": True, "detail": "No boot changes to apply", "skipped": True}
        return _patch(session, f"/redfish/v1/Systems/{system_id}", payload)

    if res_key == "power":
        desired = data.get("desired_power_state", "on")
        action_map = {
            "on": "On", "off": "ForceOff", "ForceOn": "ForceOn", "ForceOff": "ForceOff",
            "GracefulShutdown": "GracefulShutdown", "ForceRestart": "ForceRestart",
            "GracefulRestart": "GracefulRestart", "Nmi": "Nmi",
            "PushPowerButton": "PushPowerButton",
        }
        reset_type = action_map.get(desired, "On")
        return _post(session,
                      f"/redfish/v1/Systems/{system_id}/Actions/ComputerSystem.Reset",
                      {"ResetType": reset_type})

    if res_key == "identify_led":
        active = data.get("identify_led", False)
        state = "Lit" if active else "Off"
        return _patch(session, f"/redfish/v1/Systems/{system_id}",
                       {"IndicatorLED": state})

    if res_key == "secure_boot":
        payload = {"SecureBootEnable": data.get("secure_boot_enabled", False)}
        return _patch(session, f"/redfish/v1/Systems/{system_id}/SecureBoot", payload)

    if res_key == "bios_reset":
        if not data.get("reset_bios_to_default"):
            return {"ok": True, "detail": "Reset not requested", "skipped": True}
        return _post(session,
                      f"/redfish/v1/Systems/{system_id}/Bios/Actions/Bios.ResetBios", {})

    if res_key == "bmc_settings":
        manager_id = data.get("manager_id", "c885a")
        patches = {}
        ntp = data.get("ntp_servers")
        if ntp:
            patches["NTP"] = {"NTPServers": ntp}
        if patches:
            result = _patch(session, f"/redfish/v1/Managers/{manager_id}/NetworkProtocol", patches)
            if not result.get("ok"):
                return result
        if data.get("reset_bmc"):
            return _post(session,
                          f"/redfish/v1/Managers/{manager_id}/Actions/Manager.Reset",
                          {"ResetType": "GracefulRestart"})
        return {"ok": True, "status": 200}

    if res_key == "bmc_network_protocol":
        manager_id = data.get("manager_id", "c885a")
        payload = {}
        for proto, key in [("SSH", "ssh"), ("HTTPS", "https"), ("IPMI", "ipmi"),
                           ("KVMIP", "kvmip"), ("SNMP", "snmp")]:
            enabled_key = f"{key}_enabled"
            port_key = f"{key}_port"
            if enabled_key in data:
                payload[proto] = {
                    "ProtocolEnabled": data[enabled_key],
                    "Port": data.get(port_key, 0),
                }
        if not payload:
            return {"ok": True, "detail": "No protocol changes", "skipped": True}
        return _patch(session, f"/redfish/v1/Managers/{manager_id}/NetworkProtocol", payload)

    if res_key == "virtual_media":
        if not data.get("mount_virtual_media"):
            return {"ok": True, "detail": "Virtual media mount not requested", "skipped": True}
        manager_id = data.get("manager_id", "c885a")
        media_id = data.get("virtual_media_id", "CD0")
        payload = {
            "Image": data.get("virtual_media_image_url", ""),
            "TransferProtocolType": data.get("virtual_media_transfer_protocol", "HTTPS"),
            "WriteProtected": data.get("virtual_media_write_protected", True),
        }
        return _patch(session,
                       f"/redfish/v1/Managers/{manager_id}/VirtualMedia/{media_id}", payload)

    if res_key == "log_service":
        if not data.get("clear_event_log"):
            return {"ok": True, "detail": "Log clear not requested", "skipped": True}
        manager_id = data.get("manager_id", "c885a")
        log_id = data.get("log_service_id", "EventLog")
        return _post(session,
                      f"/redfish/v1/Managers/{manager_id}/LogServices/{log_id}/Actions/LogService.ClearLog",
                      {})

    if res_key == "event_subscription":
        if not data.get("create_event_subscription"):
            return {"ok": True, "detail": "Subscription not requested", "skipped": True}
        payload = {
            "Destination": data.get("event_subscription_destination", ""),
            "Protocol": data.get("event_subscription_protocol", "Redfish"),
            "Context": data.get("event_subscription_context", ""),
            "EventTypes": data.get("event_subscription_types", ["Alert"]),
        }
        return _post(session, "/redfish/v1/EventService/Subscriptions", payload)

    if res_key == "user_accounts":
        acct_id = data.get("account_id", 2)
        payload = {}
        if data.get("username"):
            payload["UserName"] = data["username"]
        if data.get("password"):
            payload["Password"] = data["password"]
        if data.get("role_id"):
            payload["RoleId"] = data["role_id"]
        payload["Enabled"] = data.get("account_enabled", True)
        if not payload.get("UserName") and not payload.get("Password"):
            return {"ok": True, "detail": "No account changes to apply", "skipped": True}
        return _patch(session, f"/redfish/v1/AccountService/Accounts/{acct_id}", payload)

    if res_key == "account_service":
        payload = {
            "AccountLockoutThreshold": data.get("account_lockout_threshold", 5),
            "AccountLockoutDuration": data.get("account_lockout_duration", 300),
            "AccountLockoutCounterResetAfter": data.get("account_lockout_counter_reset", 300),
            "MinPasswordLength": data.get("min_password_length", 8),
        }
        return _patch(session, "/redfish/v1/AccountService", payload)

    if res_key == "bmc_ethernet":
        manager_id = data.get("manager_id", "c885a")
        iface_id = data.get("interface_id", "eth0")
        payload = {}
        if data.get("hostname"):
            payload["HostName"] = data["hostname"]
        if data.get("fqdn"):
            payload["FQDN"] = data["fqdn"]
        ipv4_dhcp = data.get("ipv4_dhcp_enabled", True)
        payload["DHCPv4"] = {"DHCPEnabled": ipv4_dhcp}
        if not ipv4_dhcp and data.get("ipv4_address"):
            payload["IPv4StaticAddresses"] = [{
                "Address": data.get("ipv4_address", ""),
                "SubnetMask": data.get("ipv4_subnet_mask", "255.255.255.0"),
                "Gateway": data.get("ipv4_gateway", ""),
            }]
        if data.get("ipv6_enabled") and data.get("ipv6_address"):
            payload["IPv6StaticAddresses"] = [{
                "Address": data.get("ipv6_address", ""),
                "PrefixLength": data.get("ipv6_prefix_length", 64),
            }]
        if data.get("vlan_enabled"):
            payload["VLAN"] = {
                "VLANEnable": True,
                "VLANId": data.get("vlan_id", 0),
            }
        dns = data.get("dns_servers")
        if dns:
            payload["NameServers"] = dns
        if not payload:
            return {"ok": True, "detail": "No ethernet changes to apply", "skipped": True}
        return _patch(session,
                       f"/redfish/v1/Managers/{manager_id}/EthernetInterfaces/{iface_id}",
                       payload)

    if res_key == "chassis_thermal":
        return {"ok": True, "detail": "Thermal data is read-only. Use GET to retrieve sensor data.", "skipped": True}

    if res_key == "chassis_power":
        chassis_id = data.get("chassis_id", "1")
        if not data.get("power_limit_enabled"):
            return {"ok": True, "detail": "Power limit not enabled", "skipped": True}
        payload = {
            "PowerControl": [{
                "PowerLimit": {
                    "LimitInWatts": data.get("power_limit_watts", 0),
                    "LimitException": data.get("power_limit_exception", "NoAction"),
                }
            }]
        }
        return _patch(session, f"/redfish/v1/Chassis/{chassis_id}/Power", payload)

    if res_key == "storage":
        if not data.get("create_virtual_drive"):
            return {"ok": True, "detail": "Virtual drive creation not requested", "skipped": True}
        ctrl_id = data.get("storage_controller_id", "")
        if not ctrl_id:
            return {"ok": False, "detail": "Storage controller ID is required"}
        slots_str = data.get("drive_slots", "")
        drives = []
        if slots_str:
            for slot in slots_str.split(","):
                slot = slot.strip()
                if slot:
                    drives.append({
                        "@odata.id": f"/redfish/v1/Systems/{system_id}/Storage/{ctrl_id}/Drives/{slot}"
                    })
        payload = {
            "VolumeType": data.get("raid_type", "RAID1"),
            "Name": data.get("vd_name", "VD0"),
            "Links": {"Drives": drives} if drives else {},
            "Oem": {
                "Cisco": {
                    "StripSizeBytes": int(data.get("strip_size_kb", "256")) * 1024,
                    "ReadPolicy": data.get("read_policy", "ReadAhead"),
                    "WritePolicy": data.get("write_policy", "WriteThrough"),
                }
            },
        }
        return _post(session,
                      f"/redfish/v1/Systems/{system_id}/Storage/{ctrl_id}/Volumes",
                      payload)

    if res_key == "firmware_update":
        image_url = data.get("firmware_image_url", "")
        if not image_url:
            return {"ok": False, "detail": "Firmware image URL is required"}
        payload = {
            "ImageURI": image_url,
            "TransferProtocol": data.get("transfer_protocol", "HTTPS"),
            "@Redfish.OperationApplyTime": data.get("apply_time", "Immediate"),
            "Targets": [],
        }
        if data.get("force_update"):
            payload["ForceUpdate"] = True
        return _post(session,
                      "/redfish/v1/UpdateService/Actions/UpdateService.SimpleUpdate",
                      payload)

    if res_key == "certificate_management":
        action = data.get("action", "view")
        if action == "view":
            return {"ok": True, "detail": "Certificate viewing is read-only. Use GET to retrieve.", "skipped": True}
        if action == "generate_csr":
            payload = {
                "CertificateCollection": {
                    "@odata.id": "/redfish/v1/Managers/c885a/NetworkProtocol/HTTPS/Certificates"
                },
                "CommonName": data.get("csr_common_name", ""),
                "Organization": data.get("csr_organization", ""),
                "Country": data.get("csr_country", "US"),
            }
            return _post(session,
                          "/redfish/v1/CertificateService/Actions/CertificateService.GenerateCSR",
                          payload)
        if action == "replace":
            cert_str = data.get("certificate_string", "")
            key_str = data.get("private_key_string", "")
            if not cert_str:
                return {"ok": False, "detail": "Certificate PEM content is required"}
            payload = {
                "CertificateString": cert_str + ("\n" + key_str if key_str else ""),
                "CertificateType": data.get("certificate_type", "PEM"),
            }
            return _post(session,
                          "/redfish/v1/CertificateService/Actions/CertificateService.ReplaceCertificate",
                          payload)
        return {"ok": False, "detail": f"Unknown certificate action: {action}"}

    if res_key == "session_service":
        payload = {
            "SessionTimeout": data.get("session_timeout", 1800),
            "ServiceEnabled": data.get("service_enabled", True),
        }
        return _patch(session, "/redfish/v1/SessionService", payload)

    if res_key == "system_inventory":
        return {"ok": True, "detail": "System inventory is read-only. Use GET to retrieve.", "skipped": True}

    if res_key == "manager_reset":
        if not data.get("confirm_reset"):
            return {"ok": True, "detail": "BMC reset not confirmed", "skipped": True}
        manager_id = data.get("manager_id", "c885a")
        reset_type = data.get("reset_type", "GracefulRestart")
        return _post(session,
                      f"/redfish/v1/Managers/{manager_id}/Actions/Manager.Reset",
                      {"ResetType": reset_type})

    if res_key == "syslog_settings":
        manager_id = data.get("manager_id", "c885a")
        payload = {"Oem": {"Cisco": {"RemoteSyslog": {
            "Enabled": data.get("syslog_enabled", False),
            "Server1": data.get("syslog_server_1", ""),
            "Server2": data.get("syslog_server_2", ""),
            "Port": data.get("syslog_port", 514),
            "MinimumSeverity": data.get("syslog_minimum_severity", "Warning"),
        }}}}
        return _patch(session, f"/redfish/v1/Managers/{manager_id}", payload)

    if res_key == "snmp_settings":
        payload = {
            "SNMP": {
                "ProtocolEnabled": data.get("snmp_enabled", False),
                "Port": data.get("snmp_port", 161),
                "CommunityStrings": [{"AccessMode": "Full", "CommunityString": data.get("community_string", "public")}],
            }
        }
        manager_id = data.get("manager_id", "c885a")
        result = _patch(session, f"/redfish/v1/Managers/{manager_id}/NetworkProtocol", payload)
        trap_dests = [d for d in [
            data.get("trap_destination_1"), data.get("trap_destination_2"), data.get("trap_destination_3")
        ] if d]
        for dest in trap_dests:
            _post(session, "/redfish/v1/EventService/Subscriptions", {
                "Destination": dest,
                "Protocol": "SNMPv2c",
                "Context": "snmp-trap",
            })
        return result

    if res_key == "smtp_settings":
        manager_id = data.get("manager_id", "c885a")
        payload = {"Oem": {"Cisco": {"SMTP": {
            "Enabled": data.get("smtp_enabled", False),
            "ServerAddress": data.get("smtp_server", ""),
            "Port": data.get("smtp_port", 25),
            "FromAddress": data.get("smtp_from_address", ""),
            "Recipients": [r for r in [
                data.get("smtp_recipient_1"), data.get("smtp_recipient_2")
            ] if r],
            "MinimumSeverity": data.get("smtp_minimum_severity", "Warning"),
        }}}}
        return _patch(session, f"/redfish/v1/Managers/{manager_id}", payload)

    if res_key == "ntp_settings":
        manager_id = data.get("manager_id", "c885a")
        ntp_servers = [s for s in [
            data.get("ntp_server_1"), data.get("ntp_server_2"),
            data.get("ntp_server_3"), data.get("ntp_server_4"),
        ] if s]
        payload = {
            "NTP": {
                "NTPServers": ntp_servers,
                "ProtocolEnabled": data.get("ntp_enabled", True),
            }
        }
        result = _patch(session, f"/redfish/v1/Managers/{manager_id}/NetworkProtocol", payload)
        tz = data.get("timezone")
        if tz:
            _patch(session, f"/redfish/v1/Managers/{manager_id}", {"DateTimeLocalOffset": tz})
        return result

    if res_key == "kvm_configuration":
        manager_id = data.get("manager_id", "c885a")
        payload = {"Oem": {"Cisco": {"KVM": {
            "Enabled": data.get("kvm_enabled", True),
            "Port": data.get("kvm_port", 2068),
            "Encryption": data.get("kvm_encryption", True),
            "MaxSessions": data.get("max_kvm_sessions", 4),
            "LocalServerVideo": data.get("local_server_video", True),
        }}}}
        return _patch(session, f"/redfish/v1/Managers/{manager_id}", payload)

    return {"ok": False, "detail": f"Direct push not implemented for: {res_key}"}
