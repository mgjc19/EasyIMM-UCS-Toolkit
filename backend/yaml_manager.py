"""
YAML Manager -- reads/writes .ezi.yaml files in the EasyIMM project root.

Also reads per-domain synced data from ``domains/<fqdn>/`` subfolders
and merges it into the tree so users see what's deployed on each
connected Intersight domain alongside locally-defined resources.
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml

from paths import EASYIMM_ROOT, DOMAINS_ROOT

FILE_ROUTING = {
    "pools": {
        "ip": "pools/pools.ezi.yaml",
        "iqn": "pools/pools.ezi.yaml",
        "mac": "pools/pools.ezi.yaml",
        "resource": "pools/pools.ezi.yaml",
        "uuid": "pools/pools.ezi.yaml",
        "wwnn": "pools/pools.ezi.yaml",
        "wwpn": "pools/pools.ezi.yaml",
    },
    "policies": {
        "bios": "policies/compute.ezi.yaml",
        "boot_order": "policies/compute.ezi.yaml",
        "firmware": "policies/compute.ezi.yaml",
        "firmware_authenticate": "policies/compute.ezi.yaml",
        "memory": "policies/compute.ezi.yaml",
        "scrub": "policies/compute.ezi.yaml",
        "virtual_media": "policies/compute.ezi.yaml",
        "virtual_kvm": "policies/compute.ezi.yaml",
        "sd_card": "policies/compute.ezi.yaml",
        "imc_access": "policies/management.ezi.yaml",
        "ipmi_over_lan": "policies/management.ezi.yaml",
        "ldap": "policies/management.ezi.yaml",
        "local_user": "policies/management.ezi.yaml",
        "serial_over_lan": "policies/management.ezi.yaml",
        "certificate_management": "policies/management.ezi.yaml",
        "device_connector": "policies/management.ezi.yaml",
        "smtp": "policies/management.ezi.yaml",
        "ssh": "policies/management.ezi.yaml",
        "syslog": "policies/management.ezi.yaml",
        "snmp": "policies/management.ezi.yaml",
        "network_connectivity": "policies/domain.ezi.yaml",
        "ntp": "policies/domain.ezi.yaml",
        "flow_control": "policies/domain.ezi.yaml",
        "link_aggregation": "policies/domain.ezi.yaml",
        "link_control": "policies/domain.ezi.yaml",
        "switch_control": "policies/domain.ezi.yaml",
        "system_qos": "policies/domain.ezi.yaml",
        "multicast": "policies/domain.ezi.yaml",
        "mac_sec": "policies/domain.ezi.yaml",
        "ethernet_adapter": "policies/ethernet.ezi.yaml",
        "ethernet_network": "policies/ethernet.ezi.yaml",
        "ethernet_network_control": "policies/ethernet.ezi.yaml",
        "ethernet_network_group": "policies/ethernet.ezi.yaml",
        "ethernet_qos": "policies/ethernet.ezi.yaml",
        "fibre_channel_adapter": "policies/fibre_channel.ezi.yaml",
        "fibre_channel_network": "policies/fibre_channel.ezi.yaml",
        "fibre_channel_qos": "policies/fibre_channel.ezi.yaml",
        "fc_zone": "policies/fibre_channel.ezi.yaml",
        "lan_connectivity": "policies/lan_connectivity.ezi.yaml",
        "san_connectivity": "policies/san_connectivity.ezi.yaml",
        "vhba_template": "policies/san_connectivity.ezi.yaml",
        "vnic_template": "policies/lan_connectivity.ezi.yaml",
        "port": "policies/port.ezi.yaml",
        "power": "policies/environment.ezi.yaml",
        "thermal": "policies/environment.ezi.yaml",
        "storage": "policies/storage.ezi.yaml",
        "drive_security": "policies/storage.ezi.yaml",
        "persistent_memory": "policies/storage.ezi.yaml",
        "iscsi_adapter": "policies/storage.ezi.yaml",
        "iscsi_boot": "policies/storage.ezi.yaml",
        "iscsi_static_target": "policies/storage.ezi.yaml",
        "vlan": "policies/vlan.ezi.yaml",
        "vsan": "policies/vsan.ezi.yaml",
        "server_pool_qualification": "policies/server_pool_qualification.ezi.yaml",
    },
    "profiles": {
        "server": "profiles/server.ezi.yaml",
        "domain": "profiles/domain.ezi.yaml",
        "chassis": "profiles/chassis.ezi.yaml",
    },
    "templates": {
        "server": "templates/server.ezi.yaml",
        "domain": "templates/domain.ezi.yaml",
        "chassis": "templates/chassis.ezi.yaml",
    },
}


class YAMLManager:
    def __init__(self, root: str | None = None):
        self.root = Path(root) if root else EASYIMM_ROOT

    def _yaml_files(self) -> list[Path]:
        patterns = ["*.ezi.yaml", "o*/*.ezi.yaml", "p*/*.ezi.yaml", "t*/*.ezi.yaml"]
        files = []
        for pat in patterns:
            files.extend(self.root.glob(pat))
        return sorted(set(files))

    def _read_yaml(self, path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

    def _write_yaml(self, path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def _get_file_path(self, category: str, resource_type: str) -> Path:
        routing = FILE_ROUTING.get(category, {})
        rel = routing.get(resource_type)
        if not rel:
            rel = f"{category}/{resource_type}.ezi.yaml"
        return self.root / rel

    def get_merged_model(self) -> dict:
        merged = {}
        for f in self._yaml_files():
            data = self._read_yaml(f)
            for org, org_data in data.items():
                if org == "_placeholder":
                    continue
                if org not in merged:
                    merged[org] = {}
                if isinstance(org_data, dict):
                    for key, val in org_data.items():
                        if key in merged[org] and isinstance(merged[org][key], dict) and isinstance(val, dict):
                            for sub_key, sub_val in val.items():
                                merged[org][key][sub_key] = sub_val
                        else:
                            merged[org][key] = val
                elif org_data is True or org_data is False:
                    merged[org] = org_data
        return merged

    def get_organizations(self) -> list[str]:
        model = self.get_merged_model()
        return [k for k in model.keys() if k != "global_settings"]

    def get_resource_tree(self) -> dict:
        import re
        model = self.get_merged_model()
        tree = {}
        moid_orgs = {}

        for org, org_data in model.items():
            if org == "global_settings":
                continue
            org_tree = {"pools": {}, "policies": {}, "profiles": {}, "templates": {}}
            if isinstance(org_data, dict):
                for category in ("pools", "policies", "profiles", "templates"):
                    cat_data = org_data.get(category, {})
                    if isinstance(cat_data, dict):
                        for rtype, resources in cat_data.items():
                            if isinstance(resources, list):
                                org_tree[category][rtype] = [
                                    {"name": r.get("name", "unnamed"), "data": r, "_source": "local"}
                                    for r in resources
                                ]
                if org_data.get("create_organization") is not None:
                    org_tree["create_organization"] = org_data["create_organization"]
                if org_data.get("resource_groups"):
                    org_tree["resource_groups"] = org_data["resource_groups"]

            is_moid = bool(re.fullmatch(r"[0-9a-f]{24}", org))
            if is_moid:
                moid_orgs[org] = org_tree
            else:
                tree[org] = org_tree

        self._merge_domain_trees(tree)

        if moid_orgs:
            if "_synced_domains" not in tree:
                tree["_synced_domains"] = {}
            tree["_synced_domains"]["intersight (legacy sync)"] = moid_orgs

        return tree

    def _merge_domain_trees(self, tree: dict) -> None:
        """Merge synced domain data into the tree under _synced_domains."""
        if not DOMAINS_ROOT.exists():
            return

        synced_domains = {}

        for domain_dir in sorted(DOMAINS_ROOT.iterdir()):
            if not domain_dir.is_dir():
                continue
            domain_name = domain_dir.name
            domain_mgr = YAMLManager(root=str(domain_dir))
            domain_model = domain_mgr.get_merged_model()

            domain_orgs = {}
            for org, org_data in domain_model.items():
                if org in ("global_settings", "_placeholder"):
                    continue
                org_tree = {"pools": {}, "policies": {}, "profiles": {}, "templates": {}}
                if not isinstance(org_data, dict):
                    domain_orgs[org] = org_tree
                    continue
                for category in ("pools", "policies", "profiles", "templates"):
                    cat_data = org_data.get(category, {})
                    if not isinstance(cat_data, dict):
                        continue
                    for rtype, resources in cat_data.items():
                        if not isinstance(resources, list):
                            continue
                        org_tree[category][rtype] = [
                            {"name": r.get("name", "unnamed"), "data": r, "_source": f"synced:{domain_name}"}
                            for r in resources
                        ]
                domain_orgs[org] = org_tree

            if domain_orgs:
                synced_domains[domain_name] = domain_orgs

        if synced_domains:
            tree["_synced_domains"] = synced_domains

    def get_resources(self, org: str, category: str, resource_type: str) -> list[dict]:
        model = self.get_merged_model()
        org_data = model.get(org, {})
        if not isinstance(org_data, dict):
            return []
        cat_data = org_data.get(category, {})
        resources = cat_data.get(resource_type, [])
        return resources if isinstance(resources, list) else []

    def save_resource(self, org: str, category: str, resource_type: str, resource: dict):
        file_path = self._get_file_path(category, resource_type)
        data = self._read_yaml(file_path)

        data.pop("_placeholder", None)

        if org not in data:
            data[org] = {}
        if not isinstance(data[org], dict):
            data[org] = {}
        if category not in data[org]:
            data[org][category] = {}
        if resource_type not in data[org][category]:
            data[org][category][resource_type] = []

        resources = data[org][category][resource_type]
        name = resource.get("name", "")
        existing_idx = next(
            (i for i, r in enumerate(resources) if r.get("name") == name), None
        )
        if existing_idx is not None:
            resources[existing_idx] = resource
        else:
            resources.append(resource)

        self._write_yaml(file_path, data)

    def delete_resource(self, org: str, category: str, resource_type: str, name: str) -> bool:
        file_path = self._get_file_path(category, resource_type)
        data = self._read_yaml(file_path)

        try:
            resources = data[org][category][resource_type]
            idx = next(i for i, r in enumerate(resources) if r.get("name") == name)
            resources.pop(idx)
            if not resources:
                del data[org][category][resource_type]
            if not data[org].get(category):
                del data[org][category]
            if not data[org]:
                del data[org]
            if not data:
                data = {"_placeholder": {}}
            self._write_yaml(file_path, data)
            return True
        except (KeyError, StopIteration):
            return False

    def create_organization(self, org_name: str):
        file_path = self.root / "organizations" / "organizations.ezi.yaml"
        data = self._read_yaml(file_path)
        if org_name not in data:
            data[org_name] = {"create_organization": True}
            self._write_yaml(file_path, data)

    def delete_organization(self, org_name: str):
        for f in self._yaml_files():
            data = self._read_yaml(f)
            if org_name in data:
                del data[org_name]
                if not data:
                    data = {"_placeholder": {}}
                self._write_yaml(f, data)

    def clone_resource(
        self, src_org: str, dst_org: str, category: str, resource_type: str,
        src_name: str, dst_name: str
    ):
        resources = self.get_resources(src_org, category, resource_type)
        source = next((r for r in resources if r.get("name") == src_name), None)
        if not source:
            raise ValueError(f"Resource {src_name} not found in {src_org}/{category}/{resource_type}")
        clone = dict(source)
        clone["name"] = dst_name
        self.save_resource(dst_org, category, resource_type, clone)
