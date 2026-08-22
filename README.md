# EasyIMM UCS Toolkit

A unified web-based configuration tool for Cisco UCS infrastructure. Manage Intersight Managed Mode (IMM) policies, Redfish bare-metal servers, and visualise/audit techsupport data — all from a single interface with built-in Terraform IaC deployment.

---

## What Is This?

EasyIMM UCS Toolkit is a browser-based application that provides a visual interface for configuring and auditing Cisco UCS infrastructure. It combines three powerful capabilities into one tool:

- **Easy IMM** (Tab 1) — The community [Easy IMM](https://github.com/terraform-cisco-modules/easy-imm) Terraform module framework for Cisco Intersight Managed Mode. Manage organizations, pools, policies, profiles, and templates through interactive forms instead of editing YAML files manually. Includes live sync from Intersight, per-organisation downloads (YAML/XML), and site detail views.

- **Redfish** (Tab 2) — Comprehensive bare-metal server management via the Redfish API (e.g., Cisco C885A AI infrastructure nodes). 27 resource types covering BIOS (50+ tokens), boot order, power, storage/RAID, firmware updates, user accounts, BMC networking, certificates, KVM, SNMP, syslog, and more. Push changes directly to the BMC or use Terraform for state-managed IaC deployments. **Live state sync** reads the current configuration from the BMC so you can see what's deployed before making changes.

- **Intersight Visualiser** (Tab 3) — Upload UCS techsupport bundles (tar.gz, JSON, XML) or connect to the Intersight API to visualise the full infrastructure hierarchy — Fabric Interconnects, chassis, servers, VLANs/VSANs, service profiles, policies, and pools. Includes a **Best Practices Audit** engine (43 rules covering operational best practices and security hardening) with exportable reports (Word .docx and HTML). Supports three data modes: live Intersight API, offline techsupport, and hybrid.

Both the Easy IMM and Redfish tabs include integrated Terraform runners that let you validate, plan, apply, and destroy infrastructure directly from the browser. The Redfish provider is synced with the battle-tested [ai-pods](https://github.com/cisco/ai-pods) `cisco/redfish` v1.0.1 provider configuration.

---

## What Problem Does This Solve?

Configuring Cisco UCS infrastructure today requires:

1. **Deep Terraform/YAML knowledge** — Easy IMM uses complex nested YAML schemas. A single typo can break an entire plan.
2. **Multiple disconnected tools** — Intersight portal for cloud-managed servers, manual Redfish API calls for bare-metal, separate Terraform workspaces for each.
3. **No visual validation** — You only discover errors at `terraform plan` time, often after editing dozens of files.
4. **Documentation gap** — Design documents get out of sync with actual deployed configuration.
5. **No visibility into what's already deployed** — When building new configurations, you can't see what already exists on Intersight without switching to the portal.
6. **No quick audit capability** — Verifying your UCS configuration against Cisco best practices requires manual review of dozens of policies.

This toolkit solves all of these:

- **Visual forms with schema validation** — Every field is rendered with the correct input type, default values, and validation rules derived from the Easy IMM JSON schema.
- **Unified interface** — One tool for Intersight-managed, Redfish-managed, and techsupport-based infrastructure.
- **Live Terraform integration** — Init, plan, apply, and destroy from the UI with real-time streaming output.
- **Intersight Live Sync** — Pull existing configurations from your Intersight domain into per-domain folders. See what's deployed while building new resources.
- **Best Practices Audit** — Upload a techsupport bundle and get an instant audit against 43 Cisco best-practice and security-hardening rules, with exportable reports.
- **CiscoIQ Doc-as-Code export** — Generate `data.tech-shared.yaml` and `data.tech-ucs.yaml` files for automated documentation.
- **Download as YAML or XML** — Export individual resources, organisations, or the full state in either format.

---

## Tabs Overview

### Tab 1: Easy IMM Configuration

The primary configuration tab for managing Cisco Intersight Managed Mode infrastructure.

**Capabilities:**
- Organisation management (create, delete, clone)
- Dynamic form editor for 50+ resource types (pools, policies, profiles, templates)
- Bucketed policy tree — 45+ policies organised into logical groups (Compute, Networking, Storage & SAN, Management, Infrastructure) with per-bucket resource counts
- Clean labels matching Intersight terminology
- Schema-validated fields with dropdowns, toggles, and cross-references
- Resource cloning across organisations
- **Site Detail Panel** — Click any organisation in the tree to see a summary of all its resources (counts by category, detailed type breakdown, resource table)
- **Download per-organisation** — Export any org's data as YAML or XML from the tree or site detail panel
- **Full-state export** — Download the entire merged configuration as YAML or XML
- Intersight Live Sync (pull deployed configs into per-domain folders)
- Unsync — remove all synced domain data and clear API credentials
- Import from local workspace — point to any existing Easy IMM folder
- Import from Intersight (browse mode)
- Terraform Init / Validate / Plan / Apply / Destroy with live output

### Tab 2: Redfish Bare-Metal Configuration

Direct management of bare-metal servers via the Redfish API.

**Capabilities:**
- BMC connection management (endpoint, credentials, TLS)
- **27 configurable resource types** covering the full Redfish object model:
  - **Compute**: BIOS (50+ C885A tokens), BIOS Reset, Boot Order, Power State, Identify LED
  - **BMC Management**: BMC Settings, BMC Network Protocol, BMC Ethernet Interface, NTP Configuration
  - **Access & Security**: User Accounts, Account Service (lockout policies), Session Service, Secure Boot, Certificate Management
  - **Hardware**: Chassis Thermal (read-only sensors), Chassis Power (power capping), Storage Controllers (RAID), System Inventory (read-only)
  - **Firmware**: Firmware Update (BMC/BIOS/GPU/NIC/CPLD via UpdateService)
  - **Monitoring**: Remote Syslog, SNMP Configuration, SMTP Email Alerts, Event Subscriptions, Log Service
  - **Console**: KVM Configuration, Virtual Media
  - **Actions**: BMC Reset (graceful/force restart)
- BIOS configuration grouped by category: I/O, Server Management, Security, Memory, Processor, Power/Performance
- Enable/disable individual resources
- **Live state sync** — read current BMC config with one click
- **Two deployment methods:**
  - **Direct Push** — PATCH/POST directly to BMC Redfish API (instant, no Terraform)
  - **Terraform IaC** — Generate `.tf` files, plan, and apply with state management

### Tab 3: Intersight Visualiser & Audit

Upload techsupport bundles or connect to the Intersight API to visualise and audit your UCS infrastructure.

**Capabilities:**
- **Three data source modes:**
  - **Intersight API** — Connect with API key to visualise live policies and profiles
  - **Techsupport upload** — Parse one or more UCS techsupport bundles (.tar.gz, .tgz, .tar, .zip, .gz, .json.gz, .json, .xml)
  - **Hybrid** — Combine techsupport (physical view) with live API (logical view)
- **Hierarchical visualisation** with D3.js interactive tree:
  - Organisations → Infrastructure (FIs, Chassis, Rack Servers) → Profiles → Policies → Pools
  - Physical view, Logical view, Errors view, and Topology view
- **Best Practices Audit** — 22 operational rules derived from the Cisco Intersight Best Practices Configuration Guide:
  - General: Profile Templates, Domain Profiles
  - Storage: M.2 RAID1 Boot
  - FC/SAN: VSAN reservations, QoS data field, WWPN pool separation, vHBA redundancy, port-channels
  - Ethernet/LAN: Jumbo MTU, separate storage VLANs, RoCE failover, disjoint VLANs
  - NVMe: FC SCSI queues, TCP RX queues
  - QoS: RoCEv2 Platinum configuration
  - BIOS: VMD, IOMMU
  - iSCSI: Static IQN, MTU 9000
  - Adapter: RoCEv2 adapter policies, queue parameters
  - Firmware: Consistent FI firmware
- **Security Hardening Audit** — 21 rules from the Cisco Compute Intersight Hardening Guide:
  - Secure Boot, TPM 2.0
  - Strong passwords, Local User policy, LDAP
  - NTP, DNS, SSH policies
  - Syslog, SNMP monitoring
  - IPMI, KVM encryption, Serial over LAN
  - SED encryption, Certificate management
  - Firmware policies, USB port control, Device Connector
- **Custom rules** — Add your own audit rules with field/value matching
- **Export reports** — Download audit results as Word (.docx) or HTML with customer/project metadata
- **Search** — Filter the hierarchy tree by keyword
- **Expand/Collapse all** — Quick navigation controls
- **JSON export** — Export the full parsed hierarchy

---

## How Does It Work?

### Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                     Browser (React + MUI)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │  Easy IMM    │  │  Redfish     │  │  Intersight Visualiser │  │
│  │  Config Tab  │  │  Config Tab  │  │  (iframe → /visualiser)│  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬─────────────┘  │
└─────────┼─────────────────┼──────────────────────┼────────────────┘
          │  REST + WebSocket                      │  REST
┌─────────┼─────────────────┼──────────────────────┼────────────────┐
│         ▼                 ▼                      ▼                 │
│  ┌──────────────────────────────────┐  ┌──────────────────────┐   │
│  │   FastAPI Main App (port 8200)   │  │ Visualiser Sub-App   │   │
│  │                                  │  │ (mounted /visualiser) │   │
│  │  schema_engine   yaml_manager    │  │                      │   │
│  │  terraform_runner  redfish_mgr   │  │  techsupport_parser  │   │
│  │  intersight_sync  intersight_map │  │  best_practices      │   │
│  │  docascode_exporter              │  │  data_collector      │   │
│  └──────────────┬───────────────────┘  │  intersight_client   │   │
│                 │                       └──────────┬───────────┘   │
│  ┌──────────────▼──┐  ┌──────────────────┐        │               │
│  │  Easy IMM Root  │  │ Redfish Workspace│        ▼               │
│  │  .ezi.yaml      │  │ .tf / .tfvars    │  Parsed MO data       │
│  │  domains/<fqdn> │  │ config.json      │  (in-memory)          │
│  └────────┬────────┘  └────────┬─────────┘                       │
│           │                    │                                   │
│           ▼                    ▼                                   │
│     terraform plan/apply  terraform plan/apply                    │
│           │                    │                                   │
│           ▼                    ▼                                   │
│    Cisco Intersight API   Redfish BMC API                         │
└───────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Easy IMM tab**: The UI reads the Easy IMM JSON schema (`easy-imm.json`) to dynamically generate forms. When you edit and save a resource, the backend writes `.ezi.yaml` files to the Easy IMM Terraform root. Clicking Plan/Apply runs `terraform plan/apply` in that root directory.

2. **Redfish tab**: The UI presents configuration forms for 27 Redfish resource types. Three interaction modes:
   - **Live Sync**: Read the current live state from the BMC.
   - **Direct Push**: PATCH/POST directly to the BMC Redfish endpoints.
   - **Terraform IaC**: Generate Terraform files and deploy via the `ciscodevnet/redfish` provider.

3. **Visualiser tab**: The Intersight Visualiser runs as a FastAPI sub-application mounted at `/visualiser`. It accepts techsupport bundle uploads or Intersight API connections, parses the data into a MO (Managed Object) hierarchy, and renders it as an interactive D3.js tree. The Best Practices Audit engine runs check functions against the parsed MO data.

4. **Intersight Live Sync**: Connects to Intersight via the official Python SDK, fetches full resource objects for all 50+ resource types, maps Intersight API fields to Easy IMM YAML format, and writes the results into per-domain folders (`domains/<fqdn>/`).

5. **Export**: Maps configurations into CiscoIQ Document-as-Code YAML format, or downloads as YAML/XML at the resource, organisation, or full-state level.

---

## How to Install and Use

### Prerequisites

| Tool | Version | Required | Purpose |
|------|---------|----------|---------|
| **Python** | 3.10+ | Yes | Backend server |
| **Terraform** | 1.5+ | For deploy | Infrastructure deployment |
| **Node.js** | 18+ | For dev only | Frontend build (pre-built included) |
| **Git** | Any | For clone | Download the repository |

### Quick Start (3 steps)

```bash
# 1. Clone the repository inside your Easy IMM workspace
cd /path/to/your/easy-imm
git clone https://github.com/mgjc19/EasyIMM-UCS-Toolkit.git
cd EasyIMM-UCS-Toolkit

# 2. Start the toolkit
./run.sh

# 3. Open your browser
#    → http://localhost:8200
```

That's it. The `run.sh` script automatically:
- Detects and validates your Python installation
- Creates a virtual environment and installs all dependencies (including Visualiser)
- Builds the frontend if not already built
- Starts the server on port 8200 (serves everything: main app + visualiser)

### Connecting to Your Easy IMM Workspace

By default, the app looks for the Easy IMM Terraform files in the **parent directory** (one level up from the app folder). This works when the app folder is placed inside your Easy IMM repo:

```
your-easy-imm-repo/          ← EASYIMM_ROOT (auto-detected)
├── main.tf
├── variables.tf
├── organizations/
├── policies/
├── pools/
├── yaml_schema/
└── EasyIMM-UCS-Toolkit/     ← The app lives here
    ├── run.sh
    ├── backend/
    └── frontend/
```

If your app folder is somewhere else, point it to the Easy IMM workspace:

```bash
EASYIMM_ROOT=/path/to/your/easy-imm ./run.sh
```

### Initial Configuration

**Intersight API credentials** (required for Easy IMM tab and Visualiser live API mode):
1. Click the **Settings** (gear) icon in the toolbar
2. Enter your Intersight API Key ID
3. Enter the path to your `SecretKey.txt` file
4. Click Save

**Redfish BMC connection** (required for Redfish tab):
1. Switch to the **Redfish** tab
2. Enter the BMC endpoint URL (e.g., `https://10.0.0.1`)
3. Enter username and password
4. Click Save Connection

**Visualiser** (no configuration required):
- Upload techsupport bundles directly, or
- Connect to Intersight from within the Visualiser tab using API credentials

### Using the Visualiser Tab

1. Switch to the **Visualiser** tab (third tab in the navigation bar)
2. Choose your data source:
   - **Upload**: Click the upload icon, drag-and-drop or browse for techsupport bundles
   - **Connect**: Click the connect icon, enter Intersight API credentials
3. Once data is loaded, explore the interactive tree hierarchy
4. Switch views: Physical, Logical, Errors, Topology
5. Run audits: Click "Best Practices" or "Security Hardening" buttons
6. Export audit reports: Download as Word (.docx) or HTML

### Commands

```bash
./run.sh                           # Start in production mode (single port: 8200)
./run.sh dev                       # Start in development mode (hot-reload, ports 3100 + 8200)
./run.sh build                     # Build frontend without starting
./run.sh stop                      # Stop background dev processes
PORT=9000 ./run.sh                 # Start on a custom port
EASYIMM_ROOT=/path/to/imm ./run.sh  # Point to a different Easy IMM workspace
```

### Changing the Port

By default the toolkit runs on **port 8200**. To change it:

```bash
# One-time override
PORT=9000 ./run.sh

# Permanent change: edit run.sh and change PORT="${PORT:-8200}" to your preferred port
```

---

## Technical Construct

### Backend (Python / FastAPI)

| Module | Purpose |
|--------|---------|
| `app.py` | FastAPI application, REST + WebSocket endpoints, mounts Visualiser sub-app, static file serving |
| `paths.py` | Centralised path config — `EASYIMM_ROOT` from env var or auto-detected parent directory |
| `schema_engine.py` | Parses the Easy IMM JSON schema to generate dynamic form definitions |
| `yaml_manager.py` | CRUD operations on `.ezi.yaml` files; merges per-domain synced data into hierarchical tree |
| `terraform_runner.py` | Async subprocess runner for Terraform commands with streaming output |
| `redfish_manager.py` | 27 Redfish resource schemas, config storage, TF file generation |
| `redfish_direct.py` | Direct Redfish API push + live state reader (PATCH/POST/GET to BMC) |
| `intersight_client.py` | Intersight Python SDK wrapper with full-attribute extraction for sync |
| `intersight_mapper.py` | Per-resource-type mappers (51 types) converting Intersight API fields to Easy IMM YAML format |
| `intersight_sync.py` | Background sync engine — pulls from Intersight, resolves org MOIDs to names, writes per-domain `.ezi.yaml` |
| `config_validator.py` | Pre-flight validation of Terraform configs (cross-policy references) |
| `docascode_exporter.py` | Maps configs to CiscoIQ Document-as-Code YAML schema |
| `visualiser/` | Intersight Visualiser sub-application (mounted at `/visualiser`) |
| `visualiser/main.py` | FastAPI sub-app with upload, hierarchy, audit, and export endpoints |
| `visualiser/techsupport_parser.py` | Parses UCS techsupport bundles (tar.gz, JSON, XML) into MO hierarchies |
| `visualiser/best_practices.py` | 43 audit rules (22 best-practices + 21 security-hardening) with custom rule support |
| `visualiser/data_collector.py` | Builds hierarchy from live Intersight API data |
| `visualiser/intersight_client.py` | Async Intersight API client with HTTP Signature auth (v2 RSA, v3 ECDSA) |
| `visualiser/frontend/` | Visualiser UI (vanilla JS + D3.js, served as static files) |

### Frontend (React + Vite + Material UI)

| Component | Purpose |
|-----------|---------|
| `App.jsx` | Main shell with 3-tab navigation, toolbar, Sync/Unsync/Import/Export/Settings |
| `TreeNavigator.jsx` | Hierarchical tree with policy bucketing, org-click for site details, download icons |
| `ResourcePanel.jsx` | Dynamic form editor with YAML/XML download per resource |
| `SiteDetailPanel.jsx` | Organisation overview (resource counts, type breakdown, resource table, YAML/XML export) |
| `RedfishPanel.jsx` | Redfish server configuration with master-detail layout |
| `TerraformPanel.jsx` | Real-time Terraform command runner |
| `ImportDialog.jsx` | Multi-step import wizard for Intersight |
| `ExportDialog.jsx` | CiscoIQ Document-as-Code YAML preview and download |
| `SettingsDialog.jsx` | API key settings with "Clear Connection" button |
| `CloneDialog.jsx` | Clone resources across organisations |

### API Endpoints (Main App)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/tree` | Resource tree (local orgs + synced domains) |
| `GET` | `/api/orgs` | List organisations |
| `POST` | `/api/orgs` | Create organisation |
| `GET/POST/DELETE` | `/api/resources/...` | CRUD for resources |
| `POST` | `/api/sync` | Trigger background Intersight sync |
| `GET` | `/api/sync/status` | Poll sync progress |
| `GET` | `/api/sync/domains` | List synced domain folders |
| `DELETE` | `/api/sync/all` | Remove all synced data |
| `DELETE` | `/api/settings` | Clear saved Intersight credentials |
| `POST` | `/api/terraform/{action}` | Run Terraform (init/plan/apply/destroy) |
| `GET` | `/api/redfish/live` | Read live BMC state |
| `POST` | `/api/redfish/direct-push` | Direct push to Redfish BMC |
| `GET` | `/api/export/full-state` | Download full state as YAML |
| `GET` | `/api/export/full-state-xml` | Download full state as XML |
| `GET` | `/api/export/tech-shared` | Download CiscoIQ tech-shared YAML |
| `GET` | `/api/export/tech-ucs` | Download CiscoIQ tech-ucs YAML |

### API Endpoints (Visualiser Sub-App at `/visualiser`)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/visualiser/api/connect` | Connect to Intersight API |
| `POST` | `/visualiser/api/disconnect` | Disconnect and clear cache |
| `GET` | `/visualiser/api/status` | Current connection status |
| `GET` | `/visualiser/api/hierarchy` | Get parsed hierarchy tree (physical/logical/errors/topology) |
| `POST` | `/visualiser/api/upload` | Upload techsupport bundles (SSE progress stream) |
| `POST` | `/visualiser/api/upload/add` | Add more files to current session |
| `GET` | `/visualiser/api/export` | Export hierarchy as JSON |
| `GET` | `/visualiser/api/audit` | Run best practices / security audit |
| `GET` | `/visualiser/api/audit/rules` | Get current audit rules |
| `PUT` | `/visualiser/api/audit/rules` | Update rule settings (enable/disable/severity) |
| `POST` | `/visualiser/api/audit/rules/add` | Add custom audit rule |
| `POST` | `/visualiser/api/audit/rules/delete` | Delete custom rule |
| `GET` | `/visualiser/api/audit/export` | Export audit report as Word (.docx) |
| `GET` | `/visualiser/api/audit/export/html` | Export audit report as HTML |

### Key Technologies

- **FastAPI** — High-performance Python web framework with async support and sub-app mounting
- **WebSockets** — Real-time streaming of Terraform command output
- **React 19** — UI library with hooks-based architecture
- **Material UI 9** — Component library for consistent, accessible UI
- **Vite 8** — Fast frontend build tool
- **D3.js v7** — Interactive tree visualisation (Visualiser tab)
- **Terraform** — Infrastructure as Code engine (Intersight + Redfish providers)
- **Intersight Python SDK** — Official SDK for Cisco Intersight API
- **defusedxml** — Secure XML parsing for techsupport bundles
- **python-docx** — Word document generation for audit reports

### Project Structure

```
EasyIMM-UCS-Toolkit/                # Self-contained app folder
├── run.sh                          # One-command start script
├── README.md                       # This file
├── .gitignore
├── backend/
│   ├── requirements.txt            # Python dependencies (all-in-one)
│   ├── paths.py                    # Centralised path config
│   ├── app.py                      # FastAPI main app + Visualiser mount
│   ├── schema_engine.py            # Easy IMM schema parser
│   ├── yaml_manager.py             # YAML file manager
│   ├── terraform_runner.py         # Terraform subprocess runner
│   ├── config_validator.py         # Pre-flight config validation
│   ├── redfish_manager.py          # Redfish schemas + TF generator
│   ├── redfish_direct.py           # Direct Redfish push + live state
│   ├── intersight_client.py        # Intersight SDK client
│   ├── intersight_mapper.py        # 51 Intersight→YAML mappers
│   ├── intersight_sync.py          # Background sync engine
│   ├── docascode_exporter.py       # CiscoIQ export mapper
│   ├── visualiser/                 # Intersight Visualiser sub-app
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI sub-app (mounted at /visualiser)
│   │   ├── techsupport_parser.py   # Techsupport bundle parser
│   │   ├── best_practices.py       # 43 audit rules engine
│   │   ├── data_collector.py       # Intersight API hierarchy builder
│   │   ├── intersight_client.py    # Async Intersight client (HTTP Sig auth)
│   │   └── frontend/              # Visualiser UI (vanilla JS + D3.js)
│   │       ├── index.html
│   │       ├── app.js
│   │       ├── visualizer.js
│   │       ├── best-practices.js
│   │       └── styles.css
│   └── static/                     # Built React frontend (auto-generated)
├── frontend/
│   ├── package.json                # npm dependencies
│   ├── vite.config.js              # Vite build configuration
│   ├── src/
│   │   ├── App.jsx                 # Main app (3 tabs)
│   │   ├── api.js                  # API client
│   │   ├── theme.js                # MUI dark theme
│   │   └── components/             # React components
│   └── public/                     # Static assets
└── redfish-workspace/              # Generated Redfish TF files (runtime)
```

---

## Features at a Glance

### Easy IMM Tab
- Organisation management (create, delete, clone)
- Dynamic form editor for 50+ resource types
- Bucketed policy tree (Compute, Networking, Storage & SAN, Management, Infrastructure)
- **Site Detail Panel** — click any org to see resource counts, type breakdown, and full resource table
- **Per-resource download** — download individual resources as YAML or XML
- **Per-organisation download** — download all org data as YAML or XML
- **Full-state export** — download entire configuration as YAML or XML
- Schema-validated fields with dropdowns, toggles, and cross-references
- Resource cloning across organisations
- Intersight Live Sync with per-domain folder storage
- Unsync all — remove all synced data and clear credentials
- Import from local workspace or browse Intersight
- Terraform Init / Validate / Plan / Apply / Destroy with live output

### Redfish Tab
- BMC connection management
- 27 configurable resource types
- BIOS configuration with 50+ tokens grouped by category
- Live state sync from BMC
- Two deployment methods: Direct Push and Terraform IaC
- Independent Terraform runner

### Visualiser Tab
- Upload UCS techsupport bundles (supports .tar.gz, .tgz, .tar, .zip, .gz, .json.gz, .json, .xml)
- Connect to live Intersight API
- Hybrid mode (techsupport + API)
- Interactive D3.js tree visualisation with 4 view modes
- **Best Practices Audit** — 22 rules from Cisco Best Practices Guide
- **Security Hardening Audit** — 21 rules from Cisco Hardening Guide
- Custom rule creation with field/value pattern matching
- Export audit reports as Word (.docx) or HTML
- Search and filter the hierarchy
- JSON export of full parsed data
- SSE-based upload progress streaming

### Sync / Unsync
- Sync pulls live Intersight configurations into `domains/<fqdn>/` folders
- 51 resource type mappers cover all pools, policies, profiles, and templates
- Hierarchical tree display with domain → organisation grouping
- MOID → name resolution
- Unsync All removes all synced data with confirmation dialog
- Clear Connection removes saved API credentials

### Export
- CiscoIQ Document-as-Code export (`data.tech-shared.yaml`, `data.tech-ucs.yaml`)
- Per-resource YAML/XML download
- Per-organisation YAML/XML download
- Full-state YAML/XML download
- Visualiser audit reports (Word .docx, HTML)
- Visualiser hierarchy JSON export

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `python3: command not found` | Install Python 3.10+ from [python.org](https://www.python.org/downloads/) |
| `terraform: command not found` | Install Terraform from [terraform.io](https://developer.hashicorp.com/terraform/install). Only needed for plan/apply. |
| Port 8200 already in use | Run with a different port: `PORT=9000 ./run.sh` |
| Intersight auth fails | Verify your API Key ID and SecretKey.txt path in Settings |
| Frontend not loading | Run `./run.sh build` to rebuild the frontend |
| Sync shows 0 resources | The connected domain may not have resources of those types deployed |
| Visualiser upload fails | Ensure the file is a supported format (.tar.gz, .json, .xml, etc.) and under 2GB |
| Audit shows all "pass" | The techsupport bundle may not contain the MO types needed for specific checks |
| Visualiser shows "Not connected" | Upload a techsupport file or connect via the Intersight API from within the Visualiser tab |
| Org names show as MOIDs | Ensure Intersight credentials are configured; the tree resolves MOIDs to names |
| "Use Profile Templates" false positive | Ensure you're using the latest version — the audit now checks `_resolved_template`, `srcTempl`, `operSrcTemplName`, `SrcTemplate`, and `ucs_server_profile_template` |

---

## License

This project is provided as-is for internal and community use. It wraps the open-source [Easy IMM](https://github.com/terraform-cisco-modules/easy-imm) Terraform modules and the [Redfish Terraform provider](https://registry.terraform.io/providers/CiscoDevNet/redfish/latest).

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run in dev mode: `./run.sh dev`
4. Make changes (frontend hot-reloads, backend auto-reloads)
5. Submit a pull request
