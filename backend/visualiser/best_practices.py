"""
Best Practices Audit Engine for Cisco Intersight configurations.

Rules are derived from the Cisco Intersight Storage Best Practices
Configuration Guide and general UCS best practices.

Each rule checks parsed MO data and produces findings (pass / fail / warning).
Rules are JSON-serializable so the frontend can display and edit them.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Default rule definitions
# ---------------------------------------------------------------------------

DEFAULT_RULES: list[dict] = [
    # ── General / Templates ──
    {
        "id": "use-templates",
        "category": "General",
        "title": "Use Profile Templates",
        "description": (
            "Using a profile template is a best practice, even if your current "
            "need is for only one server profile. Working with server profile "
            "templates makes it possible to create new profiles from this template."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_use_templates",
        "reference": "Cisco Intersight Best Practice Guide — Domain Profile Template",
    },
    {
        "id": "domain-profile-exists",
        "category": "General",
        "title": "Domain Profile Applied to FI",
        "description": (
            "When a server is connected to a Fabric Interconnect, the FI "
            "should be configured with a domain profile that contains its settings."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_domain_profile",
        "reference": "Cisco Intersight Best Practice Guide — Domain Profile Template",
    },
    # ── Storage ──
    {
        "id": "m2-raid1-boot",
        "category": "Storage",
        "title": "M.2 Boot Drives in RAID1",
        "description": (
            "Best practice is to have two M.2 disks in RAID1 as a boot drive."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_m2_raid1",
        "reference": "Cisco Intersight Best Practice Guide — M.2",
    },
    # ── FC / SAN ──
    {
        "id": "vsan-not-4079",
        "category": "FC / SAN",
        "title": "VSAN 4079 Must Not Be Used",
        "description": (
            "VSAN 4079 is a reserved VSAN ID. Do not configure a VSAN as 4079. "
            "If used, Intersight will mark that VSAN with an error and raise a fault."
        ),
        "severity": "critical",
        "enabled": True,
        "check": "_check_vsan_4079",
        "reference": "Cisco Intersight Best Practice Guide — FC SAN",
    },
    {
        "id": "vsan-range-fc-switch-mode",
        "category": "FC / SAN",
        "title": "Avoid VSANs 3040–4078 in FC Switch Mode",
        "description": (
            "Do not configure VSANs in the range 3040 to 4078 when using "
            "FC switch mode."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_vsan_range_switch_mode",
        "reference": "Cisco Intersight Best Practice Guide — DAS Configuration",
    },
    {
        "id": "fc-qos-max-data-field",
        "category": "FC / SAN",
        "title": "FC QoS Max Data Field Size = 2112",
        "description": (
            "The Fibre Channel QoS policy Maximum Data Field Size should be "
            "2112 bytes."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_fc_qos_data_field",
        "reference": "Cisco Intersight Best Practice Guide — FC QoS Policy",
    },
    {
        "id": "separate-wwpn-pools",
        "category": "FC / SAN",
        "title": "Separate WWPN Pools for SAN-A and SAN-B",
        "description": (
            "Best practice is to have different WWPN pools for SAN-A and SAN-B. "
            "This makes troubleshooting easier."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_separate_wwpn_pools",
        "reference": "Cisco Intersight Best Practice Guide — SAN Connectivity",
    },
    {
        "id": "vhba-redundancy",
        "category": "FC / SAN",
        "title": "4 vHBAs per Server for Higher Redundancy",
        "description": (
            "Best practice is to have 4 vHBAs per server, for higher redundancy. "
            "Minimum 2 vHBAs (one for SAN-A, one for SAN-B)."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_vhba_redundancy",
        "reference": "Cisco Intersight Best Practice Guide — FC SAN Connectivity",
    },
    {
        "id": "san-port-channel",
        "category": "FC / SAN",
        "title": "SAN Port-Channels for FI-to-MDS",
        "description": (
            "SAN port-channels aggregate multiple physical interfaces into one "
            "logical interface to provide more bandwidth, load balancing, and "
            "link redundancy. Two different port policies are recommended, "
            "one for SAN-A and one for SAN-B."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_san_port_channel",
        "reference": "Cisco Intersight Best Practice Guide — Configure SAN Port-Channels",
    },
    # ── Ethernet / LAN ──
    {
        "id": "jumbo-mtu",
        "category": "Ethernet / LAN",
        "title": "Jumbo MTU (9000) for Storage Traffic",
        "description": (
            "Configure Jumbo MTU (9000 bytes) end-to-end and on all devices "
            "for IP-based storage (iSCSI, NVMe over TCP, NVMe over RoCEv2)."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_jumbo_mtu",
        "reference": "Cisco Intersight Best Practice Guide — External IP SAN Connectivity",
    },
    {
        "id": "separate-storage-vlans",
        "category": "Ethernet / LAN",
        "title": "Separate Storage Traffic VLANs",
        "description": (
            "Separate the storage traffic from the data traffic through "
            "different vNICs and VLANs."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_separate_storage_vlans",
        "reference": "Cisco Intersight Best Practice Guide — External IP SAN Connectivity",
    },
    {
        "id": "vnic-failover-roce",
        "category": "Ethernet / LAN",
        "title": "No Failover on RoCE vNICs",
        "description": (
            "Cisco Intersight does not support fabric failover for vNICs "
            "that have RoCE v2 enabled. Do not enable failover on RoCE vNICs."
        ),
        "severity": "critical",
        "enabled": True,
        "check": "_check_vnic_failover_roce",
        "reference": "Cisco Intersight Best Practice Guide — NVMe over RoCEv2",
    },
    # ── NVMe ──
    {
        "id": "nvme-fc-scsi-io-queues",
        "category": "NVMe",
        "title": "NVMe over FC: SCSI I/O Queues = 16",
        "description": (
            "For NVMe over FC, change the SCSI I/O Queues to 16 in the "
            "Fibre Channel adapter policy."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_nvme_fc_scsi_queues",
        "reference": "Cisco Intersight Best Practice Guide — NVMe over FC",
    },
    {
        "id": "nvme-tcp-rx-queue",
        "category": "NVMe",
        "title": "NVMe over TCP: RX Queue of 16",
        "description": (
            "The best practice is to have an RX Queue of 16 for NVMe over TCP "
            "traffic with VMware ESXi."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_nvme_tcp_rx_queue",
        "reference": "Cisco Intersight Best Practice Guide — NVMe over TCP",
    },
    # ── QoS ──
    {
        "id": "roce-qos-platinum",
        "category": "QoS",
        "title": "RoCEv2: Platinum QoS CoS5 with Jumbo MTU",
        "description": (
            "For NVMe over RoCEv2, the domain profile QoS must have Platinum "
            "enabled with no packet drops and MTU 9216."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_roce_qos_platinum",
        "reference": "Cisco Intersight Best Practice Guide — NVMe over RoCEv2",
    },
    {
        "id": "roce-eth-qos-priority",
        "category": "QoS",
        "title": "RoCEv2: Ethernet QoS Priority = Platinum",
        "description": (
            "For RoCEv2 vNICs, the Ethernet QoS policy priority should be "
            "set to Platinum with MTU 9000."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_roce_eth_qos",
        "reference": "Cisco Intersight Best Practice Guide — NVMe over RoCEv2",
    },
    # ── BIOS ──
    {
        "id": "bios-vmd-before-os",
        "category": "BIOS",
        "title": "VMD Enabled Before OS Installation",
        "description": (
            "VMD (Volume Management Device) must be enabled in the BIOS "
            "settings before the operating system is installed for Intel VROC. "
            "If it is enabled after OS installation, the server will fail to boot."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_bios_vmd",
        "reference": "Cisco Intersight Best Practice Guide — Intel VROC",
    },
    {
        "id": "bios-iommu-roce",
        "category": "BIOS",
        "title": "IOMMU Enabled for RoCEv2",
        "description": (
            "Both Intel and AMD CPUs should have IOMMU enabled for NVMe "
            "over RoCEv2 workloads."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_bios_iommu",
        "reference": "Cisco Intersight Best Practice Guide — NVMe over RoCEv2",
    },
    # ── iSCSI ──
    {
        "id": "iscsi-static-iqn",
        "category": "iSCSI",
        "title": "Use Static IQN for iSCSI Boot",
        "description": (
            "Configure static IQNs for iSCSI boot. Using a static IQN is "
            "best practice over using an IQN pool."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_iscsi_static_iqn",
        "reference": "Cisco Intersight Best Practice Guide — iSCSI Boot Configuration",
    },
    {
        "id": "iscsi-mtu-9000",
        "category": "iSCSI",
        "title": "iSCSI vNIC MTU = 9000",
        "description": (
            "Best practice is to have an MTU of 9000 for iSCSI boot vNICs."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_iscsi_mtu",
        "reference": "Cisco Intersight Best Practice Guide — iSCSI Boot Configuration",
    },
    # ── SED / Security ──
    {
        "id": "sed-drive-security",
        "category": "Security",
        "title": "SED Drive Security Policy Attached",
        "description": (
            "If SED (Self-Encrypting Drives) are in use, a Drive Security "
            "policy must be attached to the server profile. If the passphrase "
            "is lost, the drive data will be irrecoverably lost."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_sed_security",
        "reference": "Cisco Intersight Best Practice Guide — SED MRAID/RAID Controller",
    },
    # ── Adapter ──
    {
        "id": "roce-adapter-policy",
        "category": "Adapter",
        "title": "RoCEv2: Use Linux-NVMe-RoCE Adapter Policy",
        "description": (
            "When creating RoCEv2 interfaces, use the Intersight-provided "
            "Linux-NVMe-RoCE adapter policy. Do not use the default Linux "
            "adapter policy with RoCEv2."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_roce_adapter_policy",
        "reference": "Cisco Intersight Best Practice Guide — NVMe over RoCEv2",
    },
    {
        "id": "roce-queue-pairs",
        "category": "Adapter",
        "title": "RoCEv2: Queue Pairs = 1024, Memory Regions = 131072",
        "description": (
            "For RoCEv2 adapter policies: Queue Pairs = 1024, "
            "Memory Regions = 131072, Resource Groups = 8, "
            "Class of Service = 5, Interrupts = 256, Interrupt mode = MSI-x."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_roce_queue_params",
        "reference": "Cisco Intersight Best Practice Guide — NVMe over RoCEv2",
    },
    # ── Disjoint VLANs ──
    {
        "id": "disjoint-vlans",
        "category": "Ethernet / LAN",
        "title": "No Disjoint VLANs Between FI-A and FI-B",
        "description": (
            "VLANs should be consistently configured on both Fabric "
            "Interconnects. Disjoint VLANs (present on one FI but not the "
            "other) can cause traffic disruption during failover."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_disjoint_vlans",
        "reference": "UCS Best Practices — VLAN Consistency",
    },
    # ── Firmware ──
    {
        "id": "consistent-fi-firmware",
        "category": "Firmware",
        "title": "Consistent FI Firmware Versions",
        "description": (
            "Both Fabric Interconnects should run the same firmware version "
            "to avoid compatibility issues and ensure proper failover."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_fi_firmware_consistency",
        "reference": "UCS Best Practices — Firmware Management",
    },
]


# ---------------------------------------------------------------------------
# Security Hardening Rules (from Cisco Compute Intersight Hardening Guide)
# ---------------------------------------------------------------------------

SECURITY_RULES: list[dict] = [
    # ── Secure Boot & TPM ──
    {
        "id": "sec-secure-boot",
        "category": "Secure Boot",
        "title": "UEFI Secure Boot Enabled",
        "description": (
            "Cisco Secure Boot helps ensure that the code that executes on "
            "Cisco hardware platforms is authentic and unmodified. Enable "
            "UEFI Secure Boot in BIOS policy to establish a chain of trust."
        ),
        "severity": "critical",
        "enabled": True,
        "check": "_check_secure_boot",
        "reference": "Cisco Compute Intersight Hardening Guide — System Boot / Secure Boot",
    },
    {
        "id": "sec-tpm-enabled",
        "category": "Secure Boot",
        "title": "TPM 2.0 Enabled",
        "description": (
            "Trusted Platform Module 2.0 provides attestation of secure boot "
            "and protects secrets based on measured system state. TPM should "
            "be enabled in server BIOS policy."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_tpm_enabled",
        "reference": "Cisco Compute Intersight Hardening Guide — Hardware Root of Trust / TPM",
    },
    # ── Password & Authentication ──
    {
        "id": "sec-strong-password",
        "category": "Authentication",
        "title": "Strong Password Policy Enforced",
        "description": (
            "Password-strength option should be enabled. Strong passwords "
            "must contain min 8 chars, max 64, at least 3 of: lowercase, "
            "uppercase, numbers, special characters. Must not be identical "
            "to username or reversed."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_strong_password",
        "reference": "Cisco Compute Intersight Hardening Guide — Default Passwords",
    },
    {
        "id": "sec-local-user-policy",
        "category": "Authentication",
        "title": "Local User Policy Configured",
        "description": (
            "A Local User policy should be configured to manage local "
            "admin accounts on servers. Default passwords must be changed "
            "after deployment."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_local_user_policy",
        "reference": "Cisco Compute Intersight Hardening Guide — Default Passwords",
    },
    {
        "id": "sec-ldap-policy",
        "category": "Authentication",
        "title": "LDAP Policy for Centralized Authentication",
        "description": (
            "Configure LDAP policy for centralized authentication and "
            "user management instead of relying solely on local accounts."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_ldap_policy",
        "reference": "Cisco Compute Intersight Hardening Guide — Authentication Domains",
    },
    # ── Network Security ──
    {
        "id": "sec-ntp-configured",
        "category": "Network Security",
        "title": "NTP Configured and Synchronized",
        "description": (
            "Configure NTP and validate that the device time is properly "
            "synchronized. When time is not synchronized, the device "
            "connector may be unable to establish a secure TLS connection "
            "and certificates may be considered invalid."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_ntp_configured",
        "reference": "Cisco Compute Intersight Hardening Guide — Target Connections",
    },
    {
        "id": "sec-dns-configured",
        "category": "Network Security",
        "title": "DNS Configured for Device Connector",
        "description": (
            "The device connector must be able to send DNS requests and "
            "resolve DNS records. DNS used for Intersight resolution should "
            "not be hosted in the same environment being managed."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_dns_configured",
        "reference": "Cisco Compute Intersight Hardening Guide — Target Connections",
    },
    {
        "id": "sec-ssh-policy",
        "category": "Network Security",
        "title": "SSH Policy Configured",
        "description": (
            "SSH policy should be configured to control SSH access to "
            "managed endpoints. Ensure only approved cipher suites and "
            "key exchange algorithms are used."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_ssh_policy",
        "reference": "Cisco Compute Intersight Hardening Guide — FIPS / Connecting to Intersight",
    },
    # ── Monitoring & Logging ──
    {
        "id": "sec-syslog-policy",
        "category": "Monitoring",
        "title": "Syslog Policy Configured",
        "description": (
            "Configure a syslog policy to forward logs to an external "
            "syslog server. Logs include secure boot events, faults, "
            "audit entries, and security violations."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_syslog_policy",
        "reference": "Cisco Compute Intersight Hardening Guide — Endpoint Syslog / Monitoring",
    },
    {
        "id": "sec-snmp-policy",
        "category": "Monitoring",
        "title": "SNMP Policy Configured",
        "description": (
            "SNMP policy should be configured for monitoring. Use SNMPv3 "
            "with authentication and privacy for secure monitoring."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_snmp_policy",
        "reference": "Cisco Compute Intersight Hardening Guide — Monitoring with Intersight",
    },
    # ── Management Policies ──
    {
        "id": "sec-ipmi-disabled",
        "category": "Management",
        "title": "IPMI over LAN Disabled or Secured",
        "description": (
            "IPMI over LAN should be disabled unless explicitly needed. "
            "If enabled, ensure encryption key is configured."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_ipmi_policy",
        "reference": "Cisco Compute Intersight Hardening Guide — Management Policies",
    },
    {
        "id": "sec-kvm-policy",
        "category": "Management",
        "title": "KVM Policy with Encryption Enabled",
        "description": (
            "Virtual KVM policy should have encryption enabled to protect "
            "KVM sessions from eavesdropping."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_kvm_policy",
        "reference": "Cisco Compute Intersight Hardening Guide — Management Policies",
    },
    {
        "id": "sec-sol-policy",
        "category": "Management",
        "title": "Serial over LAN (SOL) Secured",
        "description": (
            "If Serial over LAN is enabled, ensure it uses SSH as the "
            "transport to prevent cleartext console access."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_sol_policy",
        "reference": "Cisco Compute Intersight Hardening Guide — Management Policies",
    },
    # ── Storage Security ──
    {
        "id": "sec-sed-encryption",
        "category": "Storage Security",
        "title": "Self-Encrypting Drives (SED) with Key Management",
        "description": (
            "For data-at-rest encryption, use Self-Encrypting Drives with "
            "remote key management (KMIP). Remote key management is the "
            "recommended method over manual/local key."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_sed_key_mgmt",
        "reference": "Cisco Compute Intersight Hardening Guide — SEDs and Drive-Security Policy",
    },
    {
        "id": "sec-certificate-mgmt",
        "category": "Certificate Management",
        "title": "Certificate Management Policy Configured",
        "description": (
            "A certificate management policy should be configured to manage "
            "certificates used for secure communication. Ensure valid "
            "CA-signed certificates are in use."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_cert_mgmt_policy",
        "reference": "Cisco Compute Intersight Hardening Guide — Encryption and Key Management",
    },
    # ── Firmware Security ──
    {
        "id": "sec-firmware-policy",
        "category": "Firmware Security",
        "title": "Firmware Policy Attached to Profiles",
        "description": (
            "Server profiles should have a firmware policy attached to "
            "ensure servers are running approved firmware versions. Image "
            "signatures guarantee firmware is valid and unmodified."
        ),
        "severity": "warning",
        "enabled": True,
        "check": "_check_firmware_policy",
        "reference": "Cisco Compute Intersight Hardening Guide — Firmware Upgrades",
    },
    # ── USB / Physical Access ──
    {
        "id": "sec-usb-disabled",
        "category": "Physical Security",
        "title": "USB Ports Disabled When Not Needed",
        "description": (
            "In a hardened posture, the USB ports should be disabled in "
            "BIOS policy. Enable them only temporarily for OS installation, "
            "then disable again."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_usb_disabled",
        "reference": "Cisco Compute Intersight Hardening Guide — Appendix D: USB OS Install",
    },
    # ── Device Connector ──
    {
        "id": "sec-device-connector",
        "category": "Device Connector",
        "title": "Device Connector Access Mode Restricted",
        "description": (
            "For standalone servers, set the device connector to 'full "
            "control from Intersight only' to restrict direct CIMC access. "
            "This prevents local configuration drift."
        ),
        "severity": "info",
        "enabled": True,
        "check": "_check_device_connector",
        "reference": "Cisco Compute Intersight Hardening Guide — Device Connector",
    },
]

# Tag rules by type for frontend filtering
for _r in DEFAULT_RULES:
    _r.setdefault("type", "best-practices")
for _r in SECURITY_RULES:
    _r.setdefault("type", "security-hardening")

DEFAULT_RULES.extend(SECURITY_RULES)


# ---------------------------------------------------------------------------
# Audit Engine
# ---------------------------------------------------------------------------

class BestPracticeAuditor:
    """Runs best-practice checks against parsed MO data."""

    def __init__(self, mos: dict[str, list[dict]], rules: list[dict] | None = None):
        self._mos = mos
        self._rules = copy.deepcopy(rules or DEFAULT_RULES)
        self._findings: list[dict] = []

    @property
    def rules(self) -> list[dict]:
        return self._rules

    @rules.setter
    def rules(self, new_rules: list[dict]):
        self._rules = copy.deepcopy(new_rules)

    def run_audit(self) -> list[dict]:
        """Execute all enabled rules and return findings."""
        self._findings = []
        for rule in self._rules:
            if not rule.get("enabled", True):
                continue
            check_name = rule.get("check", "")
            check_fn = getattr(self, check_name, None)
            if not check_fn:
                logger.warning("Unknown check function: %s", check_name)
                continue
            try:
                check_fn(rule)
            except Exception as exc:
                logger.exception("Check %s failed: %s", rule["id"], exc)
                self._findings.append({
                    "rule_id": rule["id"],
                    "rule_title": rule["title"],
                    "category": rule["category"],
                    "severity": "info",
                    "status": "error",
                    "message": f"Check failed: {exc}",
                    "affected": [],
                })
        return self._findings

    def _add_finding(self, rule: dict, status: str, message: str,
                     affected: list[str] | None = None):
        self._findings.append({
            "rule_id": rule["id"],
            "rule_title": rule["title"],
            "category": rule["category"],
            "severity": rule["severity"],
            "status": status,
            "message": message,
            "affected": affected or [],
            "reference": rule.get("reference", ""),
        })

    # ── Check implementations ──

    def _check_use_templates(self, rule: dict):
        profiles = self._mos.get("lsServer", [])
        templates = [
            p for p in profiles
            if "template" in p.get("type", "").lower()
        ]
        templates += self._mos.get("lsServerTemplate", [])

        instances = [
            p for p in profiles
            if p.get("type", "") not in ("initial-template", "updating-template", "")
            or (p.get("Moid") and "template" not in p.get("type", "").lower())
        ]

        without_template = []
        for inst in instances:
            has_template = False
            # Check resolved template (stamped by parser after full resolution)
            if inst.get("_resolved_template"):
                has_template = True
            # Check UCSM-style srcTempl
            if not has_template:
                ucsm_src = inst.get("srcTempl", "") or inst.get("operSrcTemplName", "")
                if ucsm_src:
                    has_template = True
            # Check Intersight-style SrcTemplate (MoRef dict)
            if not has_template:
                src_tmpl = inst.get("SrcTemplate")
                if isinstance(src_tmpl, dict):
                    if src_tmpl.get("Moid") or src_tmpl.get("ObjectType"):
                        has_template = True
                elif src_tmpl and str(src_tmpl).strip():
                    has_template = True
            # Check easyimm XML-style ucs_server_profile_template
            if not has_template:
                easyimm_tmpl = inst.get("ucs_server_profile_template", "")
                if easyimm_tmpl:
                    has_template = True

            if not has_template:
                name = inst.get("name", inst.get("Name", "?"))
                without_template.append(name)

        if not templates and instances:
            self._add_finding(rule, "fail",
                              f"No server profile templates found. {len(instances)} "
                              f"profile(s) exist without templates.",
                              without_template[:20])
        elif without_template:
            self._add_finding(rule, "fail",
                              f"{len(without_template)} server profile(s) are not "
                              f"derived from a template.",
                              without_template[:20])
        elif instances:
            self._add_finding(rule, "pass",
                              f"All {len(instances)} server profile(s) are derived "
                              f"from templates.")
        else:
            self._add_finding(rule, "pass",
                              "No server profiles found — check not applicable.")

    def _check_domain_profile(self, rule: dict):
        fis = self._mos.get("networkElement", [])
        clusters = self._mos.get("fabricClusterProfile", [])
        switch_profs = self._mos.get("fabricSwitchProfile", [])

        if not fis:
            self._add_finding(rule, "pass",
                              "No Fabric Interconnects detected — not applicable.")
            return

        if clusters or switch_profs:
            self._add_finding(rule, "pass",
                              f"Domain/switch profiles found: "
                              f"{len(clusters)} domain, {len(switch_profs)} switch.")
        else:
            fi_names = [f.get("dn", f.get("serial", "?")) for f in fis]
            self._add_finding(rule, "fail",
                              f"{len(fis)} Fabric Interconnect(s) detected but no "
                              f"domain profile found.",
                              fi_names[:10])

    def _check_m2_raid1(self, rule: dict):
        storage_ctrls = self._mos.get("storageController", [])
        m2_controllers = [
            c for c in storage_ctrls
            if "mstor" in (c.get("type", "") + c.get("model", "") +
                           c.get("Type", "") + c.get("Model", "")).lower()
        ]
        if not m2_controllers:
            self._add_finding(rule, "pass",
                              "No M.2 RAID controllers detected — not applicable.")
            return

        storage_policies = self._mos.get("lstorageProfile", [])
        if not storage_policies:
            self._add_finding(rule, "info",
                              f"{len(m2_controllers)} M.2 controller(s) found "
                              f"but no storage policies to verify RAID1.")
            return

        self._add_finding(rule, "info",
                          f"{len(m2_controllers)} M.2 controller(s) found. "
                          f"Verify RAID1 is configured in storage policies.")

    def _check_vsan_4079(self, rule: dict):
        vsans = self._mos.get("fabricVsan", [])
        bad = [v for v in vsans if str(v.get("id", "")) == "4079"]
        if bad:
            names = [v.get("name", f"VSAN {v.get('id')}") for v in bad]
            self._add_finding(rule, "fail",
                              f"VSAN 4079 is reserved and must not be used. "
                              f"Found {len(bad)} VSAN(s) using ID 4079.",
                              names)
        elif vsans:
            self._add_finding(rule, "pass",
                              "No VSANs using reserved ID 4079.")
        else:
            self._add_finding(rule, "pass",
                              "No VSANs configured — not applicable.")

    def _check_vsan_range_switch_mode(self, rule: dict):
        switch_ctrl = self._mos.get("fabricSwitchControlPolicy", [])
        is_switch_mode = any(
            "switch" in str(p.get("fcSwitchingMode", p.get("FcSwitchingMode", ""))).lower()
            for p in switch_ctrl
        )
        if not is_switch_mode:
            self._add_finding(rule, "pass",
                              "FC switch mode not detected — not applicable.")
            return

        vsans = self._mos.get("fabricVsan", [])
        bad = [v for v in vsans if 3040 <= _safe_int(v.get("id", "")) <= 4078]
        if bad:
            names = [f"{v.get('name', '?')} (ID {v.get('id')})" for v in bad]
            self._add_finding(rule, "fail",
                              f"{len(bad)} VSAN(s) in range 3040–4078 found while "
                              f"FC switch mode is active.",
                              names)
        else:
            self._add_finding(rule, "pass",
                              "No VSANs in restricted range 3040–4078.")

    def _check_fc_qos_data_field(self, rule: dict):
        fc_qos = self._mos.get("vnicFcQosPolicy", [])
        if not fc_qos:
            self._add_finding(rule, "pass",
                              "No FC QoS policies found — not applicable.")
            return

        bad = []
        for q in fc_qos:
            max_field = _safe_int(
                q.get("maxDataFieldSize", q.get("MaxDataFieldSize", 2112))
            )
            if max_field != 2112:
                name = q.get("name", q.get("Name", "?"))
                bad.append(f"{name} (current: {max_field})")

        if bad:
            self._add_finding(rule, "fail",
                              f"{len(bad)} FC QoS policy(ies) do not have "
                              f"Max Data Field Size = 2112.",
                              bad)
        else:
            self._add_finding(rule, "pass",
                              f"All {len(fc_qos)} FC QoS policy(ies) have "
                              f"Max Data Field Size = 2112.")

    def _check_separate_wwpn_pools(self, rule: dict):
        wwpn_pools = (
            self._mos.get("wwpnpoolPool", []) +
            self._mos.get("fcpoolInitiators", [])
        )
        if len(wwpn_pools) < 2:
            san_conns = self._mos.get("vnicSanConnPolicy", [])
            vhbas = self._mos.get("vnicFc", [])
            if san_conns or vhbas:
                self._add_finding(rule, "warning",
                                  f"Only {len(wwpn_pools)} WWPN pool(s) found. "
                                  f"Best practice is separate pools for SAN-A/B.")
            else:
                self._add_finding(rule, "pass",
                                  "No SAN connectivity — not applicable.")
        else:
            self._add_finding(rule, "pass",
                              f"{len(wwpn_pools)} WWPN pool(s) found.")

    def _check_vhba_redundancy(self, rule: dict):
        vhbas = self._mos.get("vnicFc", [])
        if not vhbas:
            self._add_finding(rule, "pass",
                              "No vHBAs configured — not applicable.")
            return

        profiles_vhba_count: dict[str, int] = {}
        for v in vhbas:
            dn = v.get("dn", "")
            prof = v.get("Profile", {})
            if isinstance(prof, dict):
                key = prof.get("Moid", dn.rsplit("/", 1)[0] if "/" in dn else "?")
            else:
                key = dn.rsplit("/", 1)[0] if "/" in dn else "?"
            profiles_vhba_count[key] = profiles_vhba_count.get(key, 0) + 1

        under = [k for k, cnt in profiles_vhba_count.items() if cnt < 2]
        ok_but_low = [k for k, cnt in profiles_vhba_count.items() if 2 <= cnt < 4]

        if under:
            self._add_finding(rule, "fail",
                              f"{len(under)} profile(s) have fewer than 2 vHBAs.",
                              under[:10])
        elif ok_but_low:
            self._add_finding(rule, "info",
                              f"{len(ok_but_low)} profile(s) have 2–3 vHBAs. "
                              f"Consider 4 vHBAs for higher redundancy.")
        else:
            self._add_finding(rule, "pass",
                              f"All profiles with vHBAs have 4+ for redundancy.")

    def _check_san_port_channel(self, rule: dict):
        fc_pcs = self._mos.get("fabricFcSanPc", [])
        fis = self._mos.get("networkElement", [])
        if not fis:
            self._add_finding(rule, "pass",
                              "No Fabric Interconnects — not applicable.")
            return

        if fc_pcs:
            self._add_finding(rule, "pass",
                              f"{len(fc_pcs)} SAN port-channel(s) configured.")
        else:
            fc_ports = self._mos.get("fabricFcSanEp", [])
            if fc_ports:
                self._add_finding(rule, "info",
                                  f"{len(fc_ports)} FC port(s) configured without "
                                  f"port-channels. Consider SAN port-channels for "
                                  f"bandwidth and redundancy.")
            else:
                self._add_finding(rule, "pass",
                                  "No FC ports configured — not applicable.")

    def _check_jumbo_mtu(self, rule: dict):
        eth_qos = self._mos.get("vnicEthQosPolicy", [])
        if not eth_qos:
            self._add_finding(rule, "pass",
                              "No Ethernet QoS policies — not applicable.")
            return

        non_jumbo = []
        for q in eth_qos:
            mtu = _safe_int(q.get("mtu", q.get("Mtu", 1500)))
            name = q.get("name", q.get("Name", "?"))
            if mtu < 9000:
                non_jumbo.append(f"{name} (MTU: {mtu})")

        if non_jumbo:
            self._add_finding(rule, "info",
                              f"{len(non_jumbo)} Ethernet QoS policy(ies) have "
                              f"MTU below 9000. This may be intentional for "
                              f"non-storage traffic.",
                              non_jumbo)
        else:
            self._add_finding(rule, "pass",
                              f"All {len(eth_qos)} Ethernet QoS policy(ies) "
                              f"have Jumbo MTU (≥ 9000).")

    def _check_separate_storage_vlans(self, rule: dict):
        vlans = self._mos.get("fabricVlan", [])
        if len(vlans) < 2:
            self._add_finding(rule, "info",
                              "Fewer than 2 VLANs configured. Consider separate "
                              "VLANs for storage and data traffic.")
        else:
            self._add_finding(rule, "pass",
                              f"{len(vlans)} VLAN(s) configured. Verify storage "
                              f"traffic uses dedicated VLANs.")

    def _check_vnic_failover_roce(self, rule: dict):
        vnics = self._mos.get("vnicEther", [])
        roce_vnics_with_failover = []
        for v in vnics:
            enable_roce = v.get("enableRoce", v.get("EnableRoce", False))
            enable_failover = v.get("failoverEnabled",
                                    v.get("FailoverEnabled", False))
            if enable_roce and enable_failover:
                name = v.get("name", v.get("Name", "?"))
                roce_vnics_with_failover.append(name)

        if roce_vnics_with_failover:
            self._add_finding(rule, "fail",
                              f"{len(roce_vnics_with_failover)} RoCE vNIC(s) "
                              f"have failover enabled. This is not supported.",
                              roce_vnics_with_failover)
        else:
            self._add_finding(rule, "pass",
                              "No RoCE vNICs with failover enabled.")

    def _check_nvme_fc_scsi_queues(self, rule: dict):
        fc_adapter_policies = self._mos.get("vnicFcAdapterPolicy", [])
        if not fc_adapter_policies:
            self._add_finding(rule, "pass",
                              "No FC Adapter policies — not applicable.")
            return

        bad = []
        for p in fc_adapter_policies:
            scsi_q = _safe_int(
                p.get("scsiQueueDepth", p.get("ScsiIoQueues", p.get("ioThrottleCount", 0)))
            )
            name = p.get("name", p.get("Name", "?"))
            if scsi_q > 0 and scsi_q != 16:
                bad.append(f"{name} (SCSI I/O Queues: {scsi_q})")

        if bad:
            self._add_finding(rule, "info",
                              f"{len(bad)} FC adapter policy(ies) may not have "
                              f"SCSI I/O Queues set to 16 for NVMe over FC.",
                              bad)
        else:
            self._add_finding(rule, "pass",
                              "FC adapter policies appear configured correctly.")

    def _check_nvme_tcp_rx_queue(self, rule: dict):
        eth_adapter_policies = self._mos.get("vnicEthAdapterPolicy", [])
        if not eth_adapter_policies:
            self._add_finding(rule, "pass",
                              "No Ethernet Adapter policies — not applicable.")
            return
        self._add_finding(rule, "info",
                          f"{len(eth_adapter_policies)} Ethernet adapter "
                          f"policy(ies) found. Verify RX Queue = 16 for "
                          f"NVMe over TCP workloads.")

    def _check_roce_qos_platinum(self, rule: dict):
        sys_qos = self._mos.get("fabricSystemQosPolicy", []) + self._mos.get("fabricQosClass", [])
        if not sys_qos:
            self._add_finding(rule, "pass",
                              "No system QoS policies — not applicable.")
            return

        platinum_found = False
        for q in sys_qos:
            name = (q.get("name", q.get("Name", "")) or "").lower()
            priority = (q.get("priority", q.get("Priority", "")) or "").lower()
            if "platinum" in name or "platinum" in priority:
                platinum_found = True
                mtu = _safe_int(q.get("mtu", q.get("Mtu", 0)))
                drop = q.get("drop", q.get("PacketDrop", q.get("adminState", "")))
                no_drop = (str(drop).lower() in ("no-drop", "false", "disabled"))
                issues = []
                if mtu > 0 and mtu < 9216:
                    issues.append(f"MTU={mtu} (need 9216)")
                if not no_drop:
                    issues.append("packet drops may be enabled")
                if issues:
                    self._add_finding(rule, "warning",
                                      f"Platinum QoS found but: {', '.join(issues)}")
                else:
                    self._add_finding(rule, "pass",
                                      "Platinum QoS properly configured.")
                break

        if not platinum_found:
            self._add_finding(rule, "info",
                              "No Platinum QoS class found. Required only if "
                              "using NVMe over RoCEv2.")

    def _check_roce_eth_qos(self, rule: dict):
        eth_qos = self._mos.get("vnicEthQosPolicy", [])
        if not eth_qos:
            self._add_finding(rule, "pass",
                              "No Ethernet QoS policies — not applicable.")
            return

        for q in eth_qos:
            priority = (q.get("priority", q.get("Priority", "")) or "").lower()
            name = q.get("name", q.get("Name", ""))
            if "roce" in name.lower() or "platinum" in priority:
                mtu = _safe_int(q.get("mtu", q.get("Mtu", 0)))
                if mtu > 0 and mtu < 9000:
                    self._add_finding(rule, "warning",
                                      f"RoCE QoS '{name}' MTU={mtu} (need 9000).")
                    return
                self._add_finding(rule, "pass",
                                  f"RoCE QoS '{name}' correctly configured.")
                return

        self._add_finding(rule, "info",
                          "No RoCE-specific Ethernet QoS policy found. "
                          "Required only for NVMe over RoCEv2.")

    def _check_bios_vmd(self, rule: dict):
        bios_policies = self._mos.get("biosPolicy", [])
        if not bios_policies:
            self._add_finding(rule, "pass",
                              "No BIOS policies — not applicable.")
            return

        for bp in bios_policies:
            vmd = bp.get("intelVmdEnable", bp.get("IntelVmdEnable", ""))
            name = bp.get("name", bp.get("Name", "?"))
            if vmd and str(vmd).lower() == "enabled":
                self._add_finding(rule, "pass",
                                  f"VMD is enabled in BIOS policy '{name}'.")
                return

        self._add_finding(rule, "info",
                          "VMD is not explicitly enabled in any BIOS policy. "
                          "Required for Intel VROC configurations.")

    def _check_bios_iommu(self, rule: dict):
        bios_policies = self._mos.get("biosPolicy", [])
        if not bios_policies:
            self._add_finding(rule, "pass",
                              "No BIOS policies — not applicable.")
            return

        for bp in bios_policies:
            iommu = bp.get("intelIOMMU", bp.get("IOMMUSupport", ""))
            name = bp.get("name", bp.get("Name", "?"))
            if iommu and str(iommu).lower() == "enabled":
                self._add_finding(rule, "pass",
                                  f"IOMMU enabled in BIOS policy '{name}'.")
                return

        self._add_finding(rule, "info",
                          "IOMMU not explicitly enabled in any BIOS policy. "
                          "Required for NVMe over RoCEv2.")

    def _check_iscsi_static_iqn(self, rule: dict):
        lan_conns = self._mos.get("vnicLanConnPolicy", [])
        if not lan_conns:
            self._add_finding(rule, "pass",
                              "No LAN connectivity policies — not applicable.")
            return

        for lc in lan_conns:
            iqn_alloc = lc.get("iqnAllocationType",
                               lc.get("IqnAllocationType", ""))
            if iqn_alloc and "pool" in str(iqn_alloc).lower():
                name = lc.get("name", lc.get("Name", "?"))
                self._add_finding(rule, "info",
                                  f"LAN policy '{name}' uses IQN pool allocation. "
                                  f"Static IQN is recommended for iSCSI boot.")
                return

        self._add_finding(rule, "pass",
                          "No IQN pool allocation detected.")

    def _check_iscsi_mtu(self, rule: dict):
        eth_qos = self._mos.get("vnicEthQosPolicy", [])
        if not eth_qos:
            self._add_finding(rule, "pass",
                              "No Ethernet QoS policies — not applicable.")
            return

        for q in eth_qos:
            name = (q.get("name", q.get("Name", "")) or "").lower()
            if "iscsi" in name:
                mtu = _safe_int(q.get("mtu", q.get("Mtu", 0)))
                if mtu > 0 and mtu < 9000:
                    self._add_finding(rule, "warning",
                                      f"iSCSI QoS '{q.get('name', q.get('Name', '?'))}' "
                                      f"has MTU={mtu}. Should be 9000.")
                    return
                self._add_finding(rule, "pass",
                                  f"iSCSI QoS '{q.get('name', q.get('Name', '?'))}' "
                                  f"has proper MTU.")
                return

        self._add_finding(rule, "pass",
                          "No iSCSI-specific QoS policy detected.")

    def _check_sed_security(self, rule: dict):
        sed_policies = self._mos.get("storageDriveSecurityPolicy", [])
        storage_local = self._mos.get("storageLocalDisk", [])

        sed_drives = [
            d for d in storage_local
            if "sed" in (d.get("type", "") + d.get("Type", "")).lower()
            or d.get("fdeCapable", d.get("FdeCapable", "")) in ("yes", "true", True)
        ]

        if not sed_drives:
            self._add_finding(rule, "pass",
                              "No SED-capable drives detected.")
            return

        if sed_policies:
            self._add_finding(rule, "pass",
                              f"{len(sed_policies)} Drive Security policy(ies) "
                              f"found for {len(sed_drives)} SED drive(s).")
        else:
            self._add_finding(rule, "info",
                              f"{len(sed_drives)} SED-capable drive(s) detected "
                              f"but no Drive Security policy found.")

    def _check_roce_adapter_policy(self, rule: dict):
        eth_adapters = self._mos.get("vnicEthAdapterPolicy", [])
        if not eth_adapters:
            self._add_finding(rule, "pass",
                              "No Ethernet adapter policies — not applicable.")
            return

        for ap in eth_adapters:
            name = (ap.get("name", ap.get("Name", "")) or "").lower()
            if "roce" in name and "nvme" not in name and "linux" not in name:
                self._add_finding(rule, "warning",
                                  f"Adapter policy '{ap.get('name', ap.get('Name', '?'))}' "
                                  f"may need to be Linux-NVMe-RoCE preset.")
                return

        self._add_finding(rule, "pass",
                          "Ethernet adapter policies appear properly named.")

    def _check_roce_queue_params(self, rule: dict):
        eth_adapters = self._mos.get("vnicEthAdapterPolicy", [])
        if not eth_adapters:
            self._add_finding(rule, "pass",
                              "No Ethernet adapter policies — not applicable.")
            return

        for ap in eth_adapters:
            name = (ap.get("name", ap.get("Name", "")) or "").lower()
            if "roce" in name or "nvme" in name:
                issues = []
                qp = _safe_int(ap.get("numQueuePairs",
                                      ap.get("NumQueuePairs", 0)))
                mr = _safe_int(ap.get("numMemRegions",
                                      ap.get("NumMemRegions", 0)))
                rg = _safe_int(ap.get("numResourceGroups",
                                      ap.get("NumResourceGroups", 0)))
                if qp > 0 and qp != 1024:
                    issues.append(f"Queue Pairs={qp} (need 1024)")
                if mr > 0 and mr != 131072:
                    issues.append(f"Memory Regions={mr} (need 131072)")
                if rg > 0 and rg != 8:
                    issues.append(f"Resource Groups={rg} (need 8)")
                if issues:
                    self._add_finding(rule, "warning",
                                      f"Adapter '{ap.get('name', ap.get('Name', '?'))}': "
                                      f"{'; '.join(issues)}")
                else:
                    self._add_finding(rule, "pass",
                                      f"Adapter '{ap.get('name', ap.get('Name', '?'))}' "
                                      f"has correct RoCEv2 parameters.")
                return

        self._add_finding(rule, "info",
                          "No RoCE-specific adapter policy found. "
                          "Required only for NVMe over RoCEv2.")

    def _check_disjoint_vlans(self, rule: dict):
        vlans = self._mos.get("fabricVlan", [])
        if not vlans:
            self._add_finding(rule, "pass",
                              "No VLANs configured — not applicable.")
            return

        a_ids: set[str] = set()
        b_ids: set[str] = set()
        for v in vlans:
            vid = str(v.get("id", ""))
            sw = v.get("switchId", v.get("SwitchId", ""))
            dn = v.get("dn", "")
            if sw == "A" or "switch-A" in dn or "fabric-a" in dn.lower():
                a_ids.add(vid)
            elif sw == "B" or "switch-B" in dn or "fabric-b" in dn.lower():
                b_ids.add(vid)
            else:
                a_ids.add(vid)
                b_ids.add(vid)

        if not a_ids and not b_ids:
            self._add_finding(rule, "pass",
                              "Cannot determine VLAN per-fabric assignment.")
            return

        only_a = a_ids - b_ids
        only_b = b_ids - a_ids
        disjoint = only_a | only_b

        if disjoint:
            details = []
            for vid in sorted(disjoint, key=lambda x: _safe_int(x)):
                if vid in only_a:
                    details.append(f"VLAN {vid} — FI-A only")
                else:
                    details.append(f"VLAN {vid} — FI-B only")
            self._add_finding(rule, "fail",
                              f"{len(disjoint)} disjoint VLAN(s) found between "
                              f"FI-A and FI-B.",
                              details[:20])
        else:
            self._add_finding(rule, "pass",
                              "All VLANs are consistent across both FIs.")

    def _check_fi_firmware_consistency(self, rule: dict):
        fis = self._mos.get("networkElement", [])
        if len(fis) < 2:
            self._add_finding(rule, "pass",
                              "Fewer than 2 FIs — consistency check not applicable.")
            return

        fw_versions: dict[str, str] = {}
        for fi in fis:
            fi_id = fi.get("id", fi.get("switchId", fi.get("SwitchId", "?")))
            fw = fi.get("firmware", fi.get("Firmware", ""))
            serial = fi.get("serial", fi.get("Serial", ""))
            if not fw:
                for fw_mo in self._mos.get("firmwareRunning", []):
                    fw_dn = fw_mo.get("dn", "")
                    fi_dn = fi.get("dn", "")
                    if fi_dn and fw_dn.startswith(fi_dn):
                        fw = fw_mo.get("version", "")
                        break
            fw_versions[f"FI-{fi_id} ({serial})"] = fw or "unknown"

        unique = set(fw_versions.values()) - {"unknown"}
        if len(unique) > 1:
            details = [f"{k}: {v}" for k, v in fw_versions.items()]
            self._add_finding(rule, "fail",
                              "Fabric Interconnects are running different "
                              "firmware versions.",
                              details)
        else:
            self._add_finding(rule, "pass",
                              "Both FIs are running the same firmware version.")

    # ===================================================================
    # Security Hardening Checks
    # ===================================================================

    def _check_secure_boot(self, rule: dict):
        """Check whether UEFI Secure Boot is enabled in BIOS policies."""
        bios_policies = self._mos.get("biosPolicy", [])
        if not bios_policies:
            self._add_finding(rule, "warning",
                              "No BIOS policies found — cannot verify Secure Boot status.")
            return
        issues: list[str] = []
        for bp in bios_policies:
            name = bp.get("name", bp.get("Name", bp.get("dn", "?")))
            sb = (bp.get("secureBoot", bp.get("SecureBoot", ""))
                  or "").lower().strip()
            if sb not in ("enabled", "platform-default"):
                issues.append(f"{name}: SecureBoot={sb or 'not set'}")
        if issues:
            self._add_finding(rule, "fail",
                              "Secure Boot is not enabled in one or more BIOS policies.",
                              issues)
        else:
            self._add_finding(rule, "pass",
                              "Secure Boot is enabled in all BIOS policies.")

    def _check_tpm_enabled(self, rule: dict):
        """Check that TPM is enabled in BIOS policies."""
        bios_policies = self._mos.get("biosPolicy", [])
        if not bios_policies:
            self._add_finding(rule, "warning",
                              "No BIOS policies found — cannot verify TPM status.")
            return
        issues: list[str] = []
        for bp in bios_policies:
            name = bp.get("name", bp.get("Name", bp.get("dn", "?")))
            tpm = (bp.get("tpmControl", bp.get("TpmControl",
                   bp.get("txtSupport", bp.get("TxtSupport", ""))))
                   or "").lower().strip()
            tpm_state = (bp.get("tpmState", bp.get("TpmState", ""))
                         or "").lower().strip()
            if tpm not in ("enabled", "platform-default") and \
               tpm_state not in ("enabled", "platform-default"):
                issues.append(f"{name}: TPM={tpm or tpm_state or 'not set'}")
        if issues:
            self._add_finding(rule, "fail",
                              "TPM is not enabled in one or more BIOS policies.",
                              issues)
        else:
            self._add_finding(rule, "pass",
                              "TPM is enabled in all BIOS policies.")

    def _check_strong_password(self, rule: dict):
        """Check if strong password enforcement is present."""
        user_policies = self._mos.get("iamEndPointUserPolicy", [])
        if not user_policies:
            self._add_finding(rule, "info",
                              "No Local User policies found — password strength "
                              "cannot be verified from uploaded data.")
            return
        issues: list[str] = []
        for up in user_policies:
            name = up.get("name", up.get("Name", up.get("dn", "?")))
            enforce = (up.get("passwordProperties", {}).get("enforceStrongPassword",
                       up.get("enforceStrongPassword",
                       up.get("EnforceStrongPassword", ""))) or "")
            if isinstance(enforce, bool):
                if not enforce:
                    issues.append(f"{name}: Strong password not enforced")
            elif isinstance(enforce, str) and enforce.lower() not in ("true", "yes", "enabled"):
                issues.append(f"{name}: Strong password={enforce or 'not set'}")
        if issues:
            self._add_finding(rule, "fail",
                              "Strong password enforcement is not enabled.",
                              issues)
        else:
            self._add_finding(rule, "pass",
                              "Strong password enforcement is enabled.")

    def _check_local_user_policy(self, rule: dict):
        """Check that a Local User policy exists."""
        policies = self._mos.get("iamEndPointUserPolicy", [])
        if not policies:
            self._add_finding(rule, "warning",
                              "No Local User policy found. Local admin accounts "
                              "may be using default passwords.")
        else:
            names = [p.get("name", p.get("Name", "?")) for p in policies]
            self._add_finding(rule, "pass",
                              f"Local User polic{'ies' if len(names) > 1 else 'y'} "
                              f"found: {', '.join(names)}")

    def _check_ldap_policy(self, rule: dict):
        """Check if LDAP policy is configured for centralized auth."""
        policies = self._mos.get("iamLdapPolicy", [])
        if not policies:
            self._add_finding(rule, "info",
                              "No LDAP policy found. Consider configuring LDAP "
                              "for centralized authentication.")
        else:
            names = [p.get("name", p.get("Name", "?")) for p in policies]
            self._add_finding(rule, "pass",
                              f"LDAP polic{'ies' if len(names) > 1 else 'y'} "
                              f"configured: {', '.join(names)}")

    def _check_ntp_configured(self, rule: dict):
        """Check NTP configuration."""
        ntp_mos = self._mos.get("commNtpProvider", [])
        if not ntp_mos:
            self._add_finding(rule, "fail",
                              "No NTP configuration found. Time synchronization "
                              "is critical for TLS certificate validation and "
                              "device connector connectivity.")
        else:
            servers: list[str] = []
            for ntp in ntp_mos:
                s = ntp.get("name", ntp.get("Name",
                    ntp.get("ntpServer", ntp.get("NtpServer", ""))))
                if s:
                    servers.append(s)
            self._add_finding(rule, "pass",
                              f"NTP configured with {len(servers)} server(s).",
                              servers or None)

    def _check_dns_configured(self, rule: dict):
        """Check DNS configuration."""
        dns_mos = self._mos.get("commDnsProvider", [])
        if not dns_mos:
            self._add_finding(rule, "warning",
                              "No DNS configuration found. The device connector "
                              "requires DNS to resolve Intersight URLs.")
        else:
            servers: list[str] = []
            for dns in dns_mos:
                s = dns.get("name", dns.get("Name",
                    dns.get("dnsServer", dns.get("DnsServer", ""))))
                if s:
                    servers.append(s)
            self._add_finding(rule, "pass",
                              f"DNS configured with {len(servers)} server(s).",
                              servers or None)

    def _check_ssh_policy(self, rule: dict):
        """Check if SSH policy is configured."""
        policies = self._mos.get("commSshPolicy", [])
        if not policies:
            self._add_finding(rule, "info",
                              "No SSH policy found. Consider configuring SSH "
                              "policy to control access and cipher suites.")
        else:
            names = [p.get("name", p.get("Name", "?")) for p in policies]
            self._add_finding(rule, "pass",
                              f"SSH polic{'ies' if len(names) > 1 else 'y'} "
                              f"configured: {', '.join(names)}")

    def _check_syslog_policy(self, rule: dict):
        """Check if syslog policy is configured."""
        policies = self._mos.get("commSyslog", [])
        if not policies:
            self._add_finding(rule, "fail",
                              "No Syslog policy found. Configure syslog to "
                              "forward security events, faults, and audit "
                              "entries to an external server.")
        else:
            names = [p.get("name", p.get("Name", "?")) for p in policies]
            self._add_finding(rule, "pass",
                              f"Syslog polic{'ies' if len(names) > 1 else 'y'} "
                              f"configured: {', '.join(names)}")

    def _check_snmp_policy(self, rule: dict):
        """Check SNMP policy configuration."""
        policies = self._mos.get("commSnmp", [])
        if not policies:
            self._add_finding(rule, "info",
                              "No SNMP policy found. Consider configuring "
                              "SNMPv3 for secure monitoring.")
        else:
            names = [p.get("name", p.get("Name", "?")) for p in policies]
            self._add_finding(rule, "pass",
                              f"SNMP polic{'ies' if len(names) > 1 else 'y'} "
                              f"configured: {', '.join(names)}")

    def _check_ipmi_policy(self, rule: dict):
        """Check IPMI over LAN policy."""
        ipmi_mos = self._mos.get("ipmiIf", [])
        if not ipmi_mos:
            self._add_finding(rule, "pass",
                              "No IPMI over LAN configuration found (disabled by default).")
            return
        issues: list[str] = []
        for ip_mo in ipmi_mos:
            name = ip_mo.get("dn", ip_mo.get("name", "?"))
            state = (ip_mo.get("adminState", ip_mo.get("AdminState", ""))
                     or "").lower()
            if state == "enabled":
                key = ip_mo.get("key", ip_mo.get("Key", ""))
                if not key:
                    issues.append(f"{name}: IPMI enabled without encryption key")
        if issues:
            self._add_finding(rule, "fail",
                              "IPMI over LAN is enabled without encryption key.",
                              issues)
        else:
            self._add_finding(rule, "pass",
                              "IPMI over LAN is properly configured or disabled.")

    def _check_kvm_policy(self, rule: dict):
        """Check KVM policy for encryption."""
        policies = self._mos.get("commKvmMgmtPolicy", [])
        if not policies:
            self._add_finding(rule, "info",
                              "No KVM policy found. KVM should have encryption enabled.")
            return
        issues: list[str] = []
        for kp in policies:
            name = kp.get("name", kp.get("Name", kp.get("dn", "?")))
            enc = (kp.get("enableEncryption", kp.get("EnableEncryption",
                   kp.get("encryption", ""))) or "")
            if isinstance(enc, bool):
                if not enc:
                    issues.append(f"{name}: KVM encryption disabled")
            elif isinstance(enc, str) and enc.lower() not in ("true", "yes", "enabled"):
                issues.append(f"{name}: KVM encryption={enc or 'not set'}")
        if issues:
            self._add_finding(rule, "fail",
                              "KVM encryption is not enabled in one or more policies.",
                              issues)
        else:
            self._add_finding(rule, "pass",
                              "KVM encryption is enabled in all KVM policies.")

    def _check_sol_policy(self, rule: dict):
        """Check Serial over LAN policy uses SSH."""
        policies = self._mos.get("solPolicy", [])
        sol_configs = self._mos.get("solConfig", [])
        all_sol = policies + sol_configs
        if not all_sol:
            self._add_finding(rule, "pass",
                              "No Serial over LAN policy found (not enabled).")
            return
        issues: list[str] = []
        for sp in all_sol:
            name = sp.get("name", sp.get("Name", sp.get("dn", "?")))
            state = (sp.get("adminState", sp.get("AdminState", ""))
                     or "").lower()
            ssh = (sp.get("sshPort", sp.get("SshPort",
                   sp.get("transport", ""))) or "")
            if state == "enabled" and not ssh:
                issues.append(f"{name}: SOL enabled, SSH transport not confirmed")
        if issues:
            self._add_finding(rule, "warning",
                              "Serial over LAN is enabled — verify SSH is used.",
                              issues)
        else:
            self._add_finding(rule, "pass",
                              "Serial over LAN is properly secured or disabled.")

    def _check_sed_key_mgmt(self, rule: dict):
        """Check SED / drive security policy for remote key management."""
        policies = self._mos.get("storageDriveSecurityPolicy", [])
        if not policies:
            self._add_finding(rule, "info",
                              "No Drive Security policy found. Consider "
                              "configuring SED with remote key management "
                              "for data-at-rest encryption.")
            return
        issues: list[str] = []
        for sp in policies:
            name = sp.get("name", sp.get("Name", sp.get("dn", "?")))
            key_setting = (sp.get("keySettingType", sp.get("KeySettingType",
                           sp.get("securityKey", ""))) or "").lower()
            if "remote" not in key_setting and "kmip" not in key_setting:
                issues.append(f"{name}: Using local/manual key instead of remote KMIP")
        if issues:
            self._add_finding(rule, "warning",
                              "Drive security uses local key management. "
                              "Remote KMIP key management is recommended.",
                              issues)
        else:
            self._add_finding(rule, "pass",
                              "Drive security uses remote key management (KMIP).")

    def _check_cert_mgmt_policy(self, rule: dict):
        """Check certificate management policy."""
        policies = self._mos.get("certmgmtPolicy", [])
        if not policies:
            self._add_finding(rule, "info",
                              "No Certificate Management policy found. "
                              "Consider configuring one to manage TLS/SSL "
                              "certificates for secure communication.")
        else:
            names = [p.get("name", p.get("Name", "?")) for p in policies]
            self._add_finding(rule, "pass",
                              f"Certificate Management polic{'ies' if len(names) > 1 else 'y'} "
                              f"configured: {', '.join(names)}")

    def _check_firmware_policy(self, rule: dict):
        """Check that firmware policies are attached to profiles."""
        fw_policies = (self._mos.get("firmwarePolicy", [])
                       + self._mos.get("firmwareComputeHostPack", []))
        profiles = self._mos.get("lsServer", [])
        if not profiles:
            profiles = self._mos.get("serverProfile", [])
        if not fw_policies:
            self._add_finding(rule, "warning",
                              "No Firmware policy found. Server profiles should "
                              "have firmware policies to ensure approved versions.")
            return
        if not profiles:
            self._add_finding(rule, "pass",
                              "Firmware policies exist (no profiles to cross-check).")
            return
        missing: list[str] = []
        for prof in profiles:
            name = prof.get("name", prof.get("Name", prof.get("dn", "?")))
            bucket = prof.get("_policyBucket", prof.get("_PolicyBucket", []))
            has_fw = False
            if isinstance(bucket, list):
                for ref in bucket:
                    otype = ""
                    if isinstance(ref, dict):
                        otype = ref.get("ObjectType", ref.get("objectType", ""))
                    elif isinstance(ref, str):
                        otype = ref
                    if "firmware" in otype.lower():
                        has_fw = True
                        break
            if not has_fw:
                missing.append(name)
        if missing:
            self._add_finding(rule, "warning",
                              "Some server profiles may lack firmware policies.",
                              missing)
        else:
            self._add_finding(rule, "pass",
                              "All server profiles have firmware policies attached.")

    def _check_usb_disabled(self, rule: dict):
        """Check if USB ports are disabled in BIOS policies."""
        bios_policies = self._mos.get("biosPolicy", [])
        if not bios_policies:
            self._add_finding(rule, "info",
                              "No BIOS policies found — cannot verify USB port status.")
            return
        issues: list[str] = []
        for bp in bios_policies:
            name = bp.get("name", bp.get("Name", bp.get("dn", "?")))
            usb = (bp.get("usbPortFront", bp.get("UsbPortFront",
                   bp.get("makeDeviceNonBootable", ""))) or "").lower()
            all_usb = (bp.get("allUsbDevices", bp.get("AllUsbDevices", ""))
                       or "").lower()
            if usb == "enabled" or all_usb == "enabled":
                issues.append(f"{name}: USB ports are enabled")
        if issues:
            self._add_finding(rule, "info",
                              "USB ports are enabled in BIOS policies. In a "
                              "hardened posture, disable USB when not needed.",
                              issues)
        else:
            self._add_finding(rule, "pass",
                              "USB ports are disabled or using platform defaults.")

    def _check_device_connector(self, rule: dict):
        """Check device connector policy for access mode."""
        policies = self._mos.get("deviceconnectorPolicy", [])
        if not policies:
            self._add_finding(rule, "info",
                              "No Device Connector policy found in uploaded data.")
            return
        issues: list[str] = []
        for dp in policies:
            name = dp.get("name", dp.get("Name", dp.get("dn", "?")))
            lock = (dp.get("lockoutEnabled",
                    dp.get("LockoutEnabled",
                    dp.get("accessMode", ""))) or "")
            if isinstance(lock, bool):
                if not lock:
                    issues.append(f"{name}: Device Connector not locked to Intersight-only")
            elif isinstance(lock, str) and lock.lower() not in ("true", "yes", "enabled",
                                                                  "read-only", "allow"):
                issues.append(f"{name}: Access mode={lock or 'not restricted'}")
        if issues:
            self._add_finding(rule, "info",
                              "Device Connector access is not restricted to "
                              "Intersight-only control.",
                              issues)
        else:
            self._add_finding(rule, "pass",
                              "Device Connector access is properly restricted.")

    # ===================================================================
    # Custom / User-defined Rule Check
    # ===================================================================

    def _check_custom_pattern(self, rule: dict):
        """Generic check for user-defined custom rules.

        The rule dict may contain:
          match_classid  – MO classId to search in (e.g. 'biosPolicy')
          match_field    – attribute name to check (e.g. 'secureBoot')
          match_value    – expected value (e.g. 'enabled'); if the MO's
                           field does NOT match this value, it's flagged.

        If no match criteria are provided, the rule simply reports the
        count of MOs for the given classId (informational).
        """
        classid = rule.get("match_classid", "")
        field = rule.get("match_field", "")
        value = (rule.get("match_value", "") or "").lower().strip()

        if not classid:
            self._add_finding(rule, "info",
                              rule.get("description", "Custom rule with no match criteria."))
            return

        mos = self._mos.get(classid, [])
        if not mos:
            self._add_finding(rule, "info",
                              f"No '{classid}' objects found in uploaded data.")
            return

        if not field:
            self._add_finding(rule, "pass",
                              f"Found {len(mos)} '{classid}' object(s).")
            return

        issues: list[str] = []
        for mo in mos:
            name = mo.get("name", mo.get("Name", mo.get("dn", "?")))
            actual = str(mo.get(field, mo.get(
                field[0].upper() + field[1:], ""))).lower().strip()
            if value and actual != value:
                issues.append(f"{name}: {field}={actual or '(empty)'} (expected: {value})")

        if issues:
            self._add_finding(rule, "fail",
                              f"Custom check failed on {len(issues)} object(s).",
                              issues)
        else:
            self._add_finding(rule, "pass",
                              f"All {len(mos)} '{classid}' object(s) match: "
                              f"{field}={value}")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_default_rules(rule_type: str | None = None) -> list[dict]:
    """Return a copy of the default rules (without internal 'check' keys).
    If *rule_type* is given, only return rules matching that type."""
    src = DEFAULT_RULES
    if rule_type:
        src = [r for r in DEFAULT_RULES if r.get("type") == rule_type]
    rules = copy.deepcopy(src)
    for r in rules:
        r.pop("check", None)
    return rules


def run_audit(mos: dict[str, list[dict]],
              rules: list[dict] | None = None) -> dict:
    """Run audit and return structured results."""
    auditor = BestPracticeAuditor(mos, rules)
    findings = auditor.run_audit()

    summary = {"pass": 0, "fail": 0, "warning": 0, "info": 0, "error": 0}
    for f in findings:
        summary[f["status"]] = summary.get(f["status"], 0) + 1

    categories: dict[str, list[dict]] = {}
    for f in findings:
        cat = f["category"]
        categories.setdefault(cat, []).append(f)

    return {
        "summary": summary,
        "total_rules_checked": len(findings),
        "categories": categories,
        "findings": findings,
    }
