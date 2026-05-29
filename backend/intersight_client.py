"""
Intersight API client for importing existing configurations.
Uses the official Cisco Intersight Python SDK for authentication.
"""

import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

RESOURCE_ENDPOINTS = {
    "pools": {
        "ip": ("ippool_api", "IppoolApi", "get_ippool_pool_list"),
        "mac": ("macpool_api", "MacpoolApi", "get_macpool_pool_list"),
        "uuid": ("uuidpool_api", "UuidpoolApi", "get_uuidpool_pool_list"),
        "iqn": ("iqnpool_api", "IqnpoolApi", "get_iqnpool_pool_list"),
        "wwnn": ("fcpool_api", "FcpoolApi", "get_fcpool_pool_list"),
        "wwpn": ("fcpool_api", "FcpoolApi", "get_fcpool_pool_list"),
        "resource": ("resourcepool_api", "ResourcepoolApi", "get_resourcepool_pool_list"),
    },
    "policies": {
        "bios": ("bios_api", "BiosApi", "get_bios_policy_list"),
        "boot_order": ("boot_api", "BootApi", "get_boot_precision_policy_list"),
        "ntp": ("ntp_api", "NtpApi", "get_ntp_policy_list"),
        "snmp": ("snmp_api", "SnmpApi", "get_snmp_policy_list"),
        "syslog": ("syslog_api", "SyslogApi", "get_syslog_policy_list"),
        "ssh": ("ssh_api", "SshApi", "get_ssh_policy_list"),
        "serial_over_lan": ("sol_api", "SolApi", "get_sol_policy_list"),
        "virtual_kvm": ("kvm_api", "KvmApi", "get_kvm_policy_list"),
        "virtual_media": ("vmedia_api", "VmediaApi", "get_vmedia_policy_list"),
        "power": ("power_api", "PowerApi", "get_power_policy_list"),
        "thermal": ("thermal_api", "ThermalApi", "get_thermal_policy_list"),
        "firmware": ("firmware_api", "FirmwareApi", "get_firmware_policy_list"),
        "imc_access": ("access_api", "AccessApi", "get_access_policy_list"),
        "ipmi_over_lan": ("ipmioverlan_api", "IpmioverlanApi", "get_ipmioverlan_policy_list"),
        "local_user": ("iam_api", "IamApi", "get_iam_end_point_user_policy_list"),
        "ldap": ("iam_api", "IamApi", "get_iam_ldap_policy_list"),
        "network_connectivity": ("networkconfig_api", "NetworkconfigApi", "get_networkconfig_policy_list"),
        "adapter_configuration": ("adapter_api", "AdapterApi", "get_adapter_config_policy_list"),
        "lan_connectivity": ("vnic_api", "VnicApi", "get_vnic_lan_connectivity_policy_list"),
        "san_connectivity": ("vnic_api", "VnicApi", "get_vnic_san_connectivity_policy_list"),
        "ethernet_adapter": ("vnic_api", "VnicApi", "get_vnic_eth_adapter_policy_list"),
        "ethernet_network": ("vnic_api", "VnicApi", "get_vnic_eth_network_policy_list"),
        "ethernet_network_control": ("fabric_api", "FabricApi", "get_fabric_eth_network_control_policy_list"),
        "ethernet_network_group": ("fabric_api", "FabricApi", "get_fabric_eth_network_group_policy_list"),
        "ethernet_qos": ("vnic_api", "VnicApi", "get_vnic_eth_qos_policy_list"),
        "fibre_channel_adapter": ("vnic_api", "VnicApi", "get_vnic_fc_adapter_policy_list"),
        "fibre_channel_network": ("vnic_api", "VnicApi", "get_vnic_fc_network_policy_list"),
        "fibre_channel_qos": ("vnic_api", "VnicApi", "get_vnic_fc_qos_policy_list"),
        "flow_control": ("fabric_api", "FabricApi", "get_fabric_flow_control_policy_list"),
        "link_aggregation": ("fabric_api", "FabricApi", "get_fabric_link_aggregation_policy_list"),
        "link_control": ("fabric_api", "FabricApi", "get_fabric_link_control_policy_list"),
        "multicast": ("fabric_api", "FabricApi", "get_fabric_multicast_policy_list"),
        "port": ("fabric_api", "FabricApi", "get_fabric_port_policy_list"),
        "switch_control": ("fabric_api", "FabricApi", "get_fabric_switch_control_policy_list"),
        "system_qos": ("fabric_api", "FabricApi", "get_fabric_system_qos_policy_list"),
        "vlan": ("fabric_api", "FabricApi", "get_fabric_vlan_list"),
        "vsan": ("fabric_api", "FabricApi", "get_fabric_vsan_list"),
        "storage": ("storage_api", "StorageApi", "get_storage_storage_policy_list"),
        "sd_card": ("sdcard_api", "SdcardApi", "get_sdcard_policy_list"),
        "smtp": ("smtp_api", "SmtpApi", "get_smtp_policy_list"),
    },
    "profiles": {
        "server": ("server_api", "ServerApi", "get_server_profile_list"),
        "chassis": ("chassis_api", "ChassisApi", "get_chassis_profile_list"),
        "domain": ("fabric_api", "FabricApi", "get_fabric_switch_cluster_profile_list"),
    },
    "templates": {
        "server": ("server_api", "ServerApi", "get_server_profile_template_list"),
    },
}


def _create_api_client(api_key_id: str, secret_key_path: str, endpoint: str = "https://intersight.com"):
    """Build an authenticated Intersight ApiClient."""
    import intersight
    from intersight.signing import (
        HttpSigningConfiguration,
        SCHEME_HS2019,
        HASH_SHA256,
        ALGORITHM_RSASSA_PKCS1v15,
        ALGORITHM_ECDSA_MODE_DETERMINISTIC_RFC6979,
        HEADER_REQUEST_TARGET,
        HEADER_HOST,
        HEADER_DATE,
        HEADER_DIGEST,
    )

    key_path = Path(secret_key_path).expanduser()
    if not key_path.exists():
        raise FileNotFoundError(f"Secret key file not found: {key_path}")

    with open(key_path, "r") as f:
        api_key = f.read()

    if re.search(r"BEGIN RSA PRIVATE KEY", api_key):
        signing_algorithm = ALGORITHM_RSASSA_PKCS1v15
    elif re.search(r"BEGIN EC PRIVATE KEY", api_key):
        signing_algorithm = ALGORITHM_ECDSA_MODE_DETERMINISTIC_RFC6979
    else:
        raise ValueError("Unrecognized key format. Expect RSA or EC private key PEM.")

    host = endpoint if endpoint.startswith("https://") else f"https://{endpoint}"

    configuration = intersight.Configuration(
        host=host,
        signing_info=HttpSigningConfiguration(
            key_id=api_key_id,
            private_key_string=api_key,
            signing_scheme=SCHEME_HS2019,
            signing_algorithm=signing_algorithm,
            hash_algorithm=HASH_SHA256,
            signed_headers=[
                HEADER_REQUEST_TARGET,
                HEADER_HOST,
                HEADER_DATE,
                HEADER_DIGEST,
            ],
        ),
    )
    return intersight.ApiClient(configuration)


_INTERNAL_FIELDS = frozenset({
    "moid", "mod_time", "create_time", "class_id", "object_type",
    "ancestors", "permission_resources", "shared_scope",
    "version_context", "account_moid", "domain_group_moid",
    "parent", "owners", "nr_account",
})


def _extract_resource(result_item, full: bool = False) -> dict:
    """Pull fields from an SDK response object.

    When *full* is True the returned dict includes a ``config`` key
    containing every settable attribute (internal/computed fields stripped).
    """
    d = result_item.to_dict() if hasattr(result_item, "to_dict") else dict(result_item)
    summary = {
        "name": d.get("name", "unnamed"),
        "moid": d.get("moid", ""),
        "description": d.get("description", ""),
        "tags": d.get("tags", []),
        "mod_time": str(d.get("mod_time", "")),
        "organization": _extract_org_name(d),
    }
    if not full:
        return summary

    config = {}
    for key, val in d.items():
        if key in _INTERNAL_FIELDS:
            continue
        if key == "organization":
            continue
        if val is None:
            continue
        if isinstance(val, dict) and val.get("class_id") == "mo.MoRef":
            config[key] = {"name": val.get("name", ""), "moid": val.get("moid", "")}
        else:
            config[key] = val
    summary["config"] = config
    return summary


def _extract_org_name(d: dict) -> str:
    """Extract org name from the Organization MoRef."""
    org = d.get("organization")
    if isinstance(org, dict):
        return org.get("name", org.get("moid", "default"))
    return "default"


class IntersightClient:
    """Thin wrapper around the Intersight Python SDK."""

    def __init__(self, api_key_id: str, secret_key_path: str, endpoint: str = "https://intersight.com"):
        self.api_client = _create_api_client(api_key_id, secret_key_path, endpoint)
        self._api_cache = {}

    def _get_api_instance(self, module_name: str, class_name: str):
        """Lazily import and cache an API class instance."""
        cache_key = f"{module_name}.{class_name}"
        if cache_key not in self._api_cache:
            import importlib
            mod = importlib.import_module(f"intersight.api.{module_name}")
            cls = getattr(mod, class_name)
            self._api_cache[cache_key] = cls(self.api_client)
        return self._api_cache[cache_key]

    def test_connection(self) -> dict:
        """Verify credentials by fetching the account info."""
        try:
            from intersight.api import iam_api
            api = iam_api.IamApi(self.api_client)
            result = api.get_iam_account_list()
            accounts = result.results or []
            if accounts:
                acct = accounts[0].to_dict()
                return {
                    "ok": True,
                    "account_name": acct.get("name", ""),
                    "moid": acct.get("moid", ""),
                }
            return {"ok": True, "account_name": "connected"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def list_organizations(self) -> list:
        """Get all organizations from Intersight."""
        try:
            from intersight.api import organization_api
            api = organization_api.OrganizationApi(self.api_client)
            result = api.get_organization_organization_list()
            return [
                {"name": o.name, "moid": o.moid, "description": getattr(o, "description", "")}
                for o in (result.results or [])
            ]
        except Exception as exc:
            logger.error("Failed to list organizations: %s", exc)
            return []

    def list_resources(
        self, category: str, resource_type: str,
        org_filter: str = None, full: bool = False,
    ) -> list:
        """List all resources of a given type from Intersight.

        When *full* is True each item includes a ``config`` dict with all
        settable attributes (needed for the sync feature).
        """
        endpoints = RESOURCE_ENDPOINTS.get(category, {})
        endpoint = endpoints.get(resource_type)
        if not endpoint:
            return []

        module_name, class_name, method_name = endpoint
        try:
            api = self._get_api_instance(module_name, class_name)
            list_method = getattr(api, method_name)

            kwargs = {"top": 100}
            if org_filter:
                kwargs["filter"] = f"Organization.Name eq '{org_filter}'"

            result = list_method(**kwargs)
            items = result.results or []
            return [_extract_resource(item, full=full) for item in items]
        except Exception as exc:
            logger.warning("Failed to list %s/%s: %s", category, resource_type, exc)
            return []

    def list_all_resources(self, org_filter: str = None, full: bool = False) -> dict:
        """Fetch all supported resource types from Intersight.

        Returns ``{category: {resource_type: [resources]}}``.
        When *full* is True, each resource includes a ``config`` body.
        """
        result = {}
        for category, types in RESOURCE_ENDPOINTS.items():
            result[category] = {}
            for resource_type in types:
                items = self.list_resources(
                    category, resource_type, org_filter, full=full,
                )
                if items:
                    result[category][resource_type] = items
        return result

    def close(self):
        if self.api_client:
            self.api_client.close()
