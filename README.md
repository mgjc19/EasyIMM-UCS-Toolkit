# EasyIMM UCS Toolkit

A unified web-based configuration tool for Cisco UCS infrastructure. Manage Intersight Managed Mode (IMM) policies, Redfish bare-metal servers, and export documentation -- all from a single interface with built-in Terraform IaC deployment.

---

## What Is This?

EasyIMM UCS Toolkit is a browser-based application that provides a visual interface for configuring Cisco UCS infrastructure. It wraps two powerful Terraform ecosystems into one tool:

- **Easy IMM** -- The community [Easy IMM](https://github.com/terraform-cisco-modules/easy-imm) Terraform module framework for Cisco Intersight Managed Mode. Manage organizations, pools, policies, profiles, and templates through interactive forms instead of editing YAML files manually.

- **Redfish** -- Comprehensive bare-metal server management via the Redfish API (e.g., Cisco C885A AI infrastructure nodes). 27 resource types covering BIOS (50+ tokens), boot order, power, storage/RAID, firmware updates, user accounts, BMC networking, certificates, KVM, SNMP, syslog, and more. Push changes directly to the BMC or use Terraform for state-managed IaC deployments. **Live state sync** reads the current configuration from the BMC so you can see what's deployed before making changes.

Both tabs include integrated Terraform runners that let you validate, plan, apply, and destroy infrastructure directly from the browser.

---

## What Problem Does This Solve?

Configuring Cisco UCS infrastructure today requires:

1. **Deep Terraform/YAML knowledge** -- Easy IMM uses complex nested YAML schemas. A single typo can break an entire plan.
2. **Multiple disconnected tools** -- Intersight portal for cloud-managed servers, manual Redfish API calls for bare-metal, separate Terraform workspaces for each.
3. **No visual validation** -- You only discover errors at `terraform plan` time, often after editing dozens of files.
4. **Documentation gap** -- Design documents get out of sync with actual deployed configuration.
5. **No visibility into what's already deployed** -- When building new configurations, you can't see what already exists on Intersight without switching to the portal.

This toolkit solves all of these:

- **Visual forms with schema validation** -- Every field is rendered with the correct input type, default values, and validation rules derived from the Easy IMM JSON schema.
- **Unified interface** -- One tool for both Intersight-managed and Redfish-managed infrastructure.
- **Live Terraform integration** -- Init, plan, apply, and destroy from the UI with real-time streaming output.
- **Intersight Live Sync** -- Pull existing configurations from your Intersight domain into per-domain folders. See what's deployed while building new resources.
- **Unsync** -- Remove synced domain data when no longer needed, keeping your workspace clean.
- **CiscoIQ Doc-as-Code export** -- Generate `data.tech-shared.yaml` and `data.tech-ucs.yaml` files that can be imported into the CiscoIQ platform for automated documentation.

---

## How Does It Work?

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Browser (React + MUI)              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │  Easy IMM    │  │  Redfish     │  │  Export /  │  │
│  │  Config Tab  │  │  Config Tab  │  │  Import    │  │
│  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘  │
└─────────┼─────────────────┼────────────────┼────────┘
          │  REST + WebSocket               │
┌─────────┼─────────────────┼────────────────┼────────┐
│         ▼                 ▼                ▼         │
│  ┌─────────────────────────────────────────────┐     │
│  │            FastAPI Backend (Python)          │     │
│  │                                             │     │
│  │  schema_engine.py   Parse easy-imm.json     │     │
│  │  yaml_manager.py    Read/write .ezi.yaml    │     │
│  │  terraform_runner   Stream TF commands      │     │
│  │  redfish_manager    Redfish TF generation   │     │
│  │  intersight_client  Intersight SDK import   │     │
│  │  intersight_sync    Live sync engine        │     │
│  │  intersight_mapper  API→YAML field mappers  │     │
│  │  docascode_exporter CiscoIQ YAML export     │     │
│  └──────────────┬──────────────────┬───────────┘     │
│                 │                  │                  │
│  ┌──────────────▼──┐  ┌───────────▼──────────┐      │
│  │  Easy IMM Root  │  │  Redfish Workspace   │      │
│  │  .ezi.yaml      │  │  .tf / .tfvars       │      │
│  │  Terraform HCL  │  │  config.json         │      │
│  │  domains/<fqdn> │  │                      │      │
│  └────────┬────────┘  └──────────┬───────────┘      │
│           │                      │                   │
│           ▼                      ▼                   │
│     terraform plan/apply   terraform plan/apply      │
│           │                      │                   │
│           ▼                      ▼                   │
│    Cisco Intersight API    Redfish BMC API            │
└──────────────────────────────────────────────────────┘
```

### Data Flow

1. **Easy IMM tab**: The UI reads the Easy IMM JSON schema (`easy-imm.json`) to dynamically generate forms. When you edit and save a resource, the backend writes `.ezi.yaml` files to the Easy IMM Terraform root. Clicking Plan/Apply runs `terraform plan/apply` in that root directory.

2. **Redfish tab**: The UI presents configuration forms for 27 Redfish resource types (BIOS with 50+ C885A-specific tokens, boot order, power, storage/RAID, firmware, user accounts, BMC networking, certificates, KVM, SNMP, syslog, and more). Three interaction modes:
   - **Live Sync**: Click the cloud-sync icon to read the current live state from the BMC. Each resource shows a "Live BMC State Available" banner with a "Load Live Values" button to populate the form with actual server values.
   - **Direct Push**: Sends REST API calls (PATCH/POST) directly to the BMC Redfish endpoints -- instant, no Terraform required.
   - **Terraform IaC**: Clicks "Generate TF" to create Terraform files (`provider.tf`, `variables.tf`, `main.tf`, `terraform.tfvars`) in the Redfish workspace. Then Init/Plan/Apply deploys via the `ciscodevnet/redfish` Terraform provider with full state management.

3. **Intersight Live Sync**: Connects to Intersight via the official Python SDK, fetches full resource objects for all 50+ resource types, maps Intersight API fields to Easy IMM YAML format, and writes the results into per-domain folders (`domains/<fqdn>/`). Organization MOIDs are resolved to their actual names before saving. The tree displays synced resources in a dedicated **"Synced from Intersight"** section, grouped by domain and then by organization -- clearly separated from your local configuration.

4. **Unsync**: Removes a domain folder and all its synced data, instantly cleaning the tree of that domain's resources. Also handles legacy synced data (MOID-named organizations stored in the main YAML files from older syncs).

5. **Import (browse)**: Lighter-weight alternative to sync -- connects to Intersight to list resources without writing files. Useful for quick exploration.

6. **Export**: Maps both Easy IMM and Redfish configurations into CiscoIQ Document-as-Code YAML format for automated documentation generation.

### Per-Domain Folder Structure

When you sync from an Intersight domain, the toolkit creates a folder under `domains/` named after the domain FQDN. This folder mirrors the standard Easy IMM directory layout:

```
domains/
└── intersight.com/
    ├── organizations/
    │   └── organizations.ezi.yaml
    ├── pools/
    │   └── pools.ezi.yaml
    ├── policies/
    │   ├── compute.ezi.yaml
    │   ├── management.ezi.yaml
    │   ├── domain.ezi.yaml
    │   ├── ethernet.ezi.yaml
    │   ├── fibre_channel.ezi.yaml
    │   ├── lan_connectivity.ezi.yaml
    │   ├── san_connectivity.ezi.yaml
    │   ├── environment.ezi.yaml
    │   ├── storage.ezi.yaml
    │   ├── vlan.ezi.yaml
    │   ├── vsan.ezi.yaml
    │   └── port.ezi.yaml
    ├── profiles/
    │   ├── server.ezi.yaml
    │   ├── domain.ezi.yaml
    │   └── chassis.ezi.yaml
    └── templates/
        └── server.ezi.yaml
```

Each domain folder is independently managed:
- **Sync** pulls the latest configs from Intersight and writes/updates the files
- **Unsync** deletes the entire domain folder
- **Multiple domains** are supported simultaneously -- each gets its own folder
- **No conflict with local files** -- synced resources are merged into the tree view but stored separately from your local `.ezi.yaml` files

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
# 1. Clone the repository
git clone https://github.com/mgjc19/EasyIMM-UCS-Toolkit.git
cd EasyIMM-UCS-Toolkit

# 2. Start the toolkit
./run.sh

# 3. Open your browser
#    → http://localhost:8200
```

That's it. The `run.sh` script automatically:
- Detects and validates your Python installation
- Creates a virtual environment and installs dependencies
- Builds the frontend if not already built
- Starts the server on port 8200

### Initial Configuration

**Intersight API credentials** (required for Easy IMM tab):
1. Click the **Settings** (gear) icon in the toolbar
2. Enter your Intersight API Key ID
3. Enter the path to your `SecretKey.txt` file
4. Click Save

**Redfish BMC connection** (required for Redfish tab):
1. Switch to the **Redfish** tab
2. Enter the BMC endpoint URL (e.g., `https://10.0.0.1`)
3. Enter username and password
4. Click Save Connection

### Syncing from Intersight

Once your API credentials are configured:

1. Click the **Sync** button (circular arrow icon) in the Easy IMM toolbar
2. The sync runs in the background -- a progress indicator shows which resource type is being fetched
3. When complete, the tree refreshes with all synced resources visible
4. Synced resources are stored in `domains/<fqdn>/` and tagged in the tree as "synced"

To **remove synced data**, click the **Unsync** button (crossed-out sync icon) and select the domain to remove.

### Commands

```bash
./run.sh              # Start in production mode (single port: 8200)
./run.sh dev          # Start in development mode (hot-reload, ports 3100 + 8200)
./run.sh build        # Build frontend without starting
./run.sh stop         # Stop background dev processes
PORT=9000 ./run.sh    # Start on a custom port
```

### Changing the Port

By default the toolkit runs on **port 8200**. If that port is already in use by another application, you can change it in two ways:

**Option 1 -- One-time override (recommended)**

Set the `PORT` environment variable before running:

```bash
PORT=9000 ./run.sh
```

The app will start on http://localhost:9000 instead.

**Option 2 -- Find an available port first**

If you're not sure which ports are free, check what's in use:

```bash
# macOS / Linux
lsof -i :8200          # Check if 8200 is taken
lsof -i -P | grep LISTEN   # See all ports in use

# Windows (PowerShell)
netstat -ano | findstr :8200
```

Then pick any unused port (e.g., 3000, 5000, 9000, 8080) and start with:

```bash
PORT=<your-port> ./run.sh
```

**Option 3 -- Permanent change**

To always use a different port, edit `run.sh` and change the default:

```bash
# Near the top of run.sh, change:
PORT="${PORT:-8200}"
# To your preferred port, e.g.:
PORT="${PORT:-9000}"
```

> **Note:** In development mode (`./run.sh dev`), the Vite dev server runs on port 3100 and the backend on the configured port (default 8200). Only the backend port is configurable via `PORT`.

---

## Technical Construct

### Backend (Python / FastAPI)

| Module | Purpose |
|--------|---------|
| `app.py` | FastAPI application, REST + WebSocket endpoints, static file serving |
| `schema_engine.py` | Parses the Easy IMM JSON schema to generate dynamic form definitions |
| `yaml_manager.py` | CRUD operations on `.ezi.yaml` files; merges per-domain synced data into hierarchical tree; detects legacy MOID orgs |
| `terraform_runner.py` | Async subprocess runner for Terraform commands with streaming output |
| `redfish_manager.py` | 27 Redfish resource schemas, config storage, TF file generation |
| `redfish_direct.py` | Direct Redfish API push + live state reader (PATCH/POST/GET to BMC) |
| `intersight_client.py` | Intersight Python SDK wrapper with full-attribute extraction for sync |
| `intersight_mapper.py` | Per-resource-type mappers (51 types) that convert Intersight API fields to Easy IMM YAML format |
| `intersight_sync.py` | Background sync engine -- pulls from Intersight, resolves org MOIDs to names, maps and writes per-domain `.ezi.yaml` files |
| `docascode_exporter.py` | Maps configs to CiscoIQ Document-as-Code YAML schema |

### Frontend (React + Vite + Material UI)

| Component | Purpose |
|-----------|---------|
| `App.jsx` | Main shell with tab navigation, toolbar with Sync/Unsync/Import/Export/Settings buttons |
| `TreeNavigator.jsx` | Hierarchical tree: local orgs at top, synced domains grouped by Intersight domain → organization with MOID→name resolution |
| `ResourcePanel.jsx` | Dynamic form editor for any Easy IMM resource |
| `RedfishPanel.jsx` | Redfish server configuration with master-detail layout |
| `TerraformPanel.jsx` | Real-time Terraform command runner (Easy IMM) |
| `ImportDialog.jsx` | Multi-step import wizard for Intersight |
| `ExportDialog.jsx` | CiscoIQ Document-as-Code YAML preview and download |
| `SettingsDialog.jsx` | API key and connection settings |
| `CloneDialog.jsx` | Clone resources across organizations |

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/tree` | Resource tree (local orgs + synced domains with MOID→name map) |
| `GET` | `/api/orgs` | List organizations |
| `POST` | `/api/orgs` | Create organization |
| `GET/POST/DELETE` | `/api/resources/...` | CRUD for resources |
| `POST` | `/api/sync` | Trigger background Intersight sync |
| `GET` | `/api/sync/status` | Poll sync progress |
| `GET` | `/api/sync/domains` | List synced domain folders |
| `DELETE` | `/api/sync/domains/{name}` | Unsync (remove) a domain |
| `POST` | `/api/import/test` | Test Intersight connection |
| `GET` | `/api/import/orgs` | List Intersight orgs |
| `POST` | `/api/import/resources` | Browse Intersight resources |
| `POST` | `/api/terraform/{action}` | Run Terraform (init/plan/apply/destroy) |
| `GET` | `/api/redfish/live` | Read live BMC state for all resource types |
| `POST` | `/api/redfish/direct-push` | Direct push to Redfish BMC |
| `POST` | `/api/redfish/generate` | Generate Redfish Terraform files |
| `GET` | `/api/export/tech-shared` | Download CiscoIQ tech-shared YAML |
| `GET` | `/api/export/tech-ucs` | Download CiscoIQ tech-ucs YAML |

### Key Technologies

- **FastAPI** -- High-performance Python web framework with async support
- **WebSockets** -- Real-time streaming of Terraform command output
- **React 19** -- UI library with hooks-based architecture
- **Material UI 9** -- Component library for consistent, accessible UI
- **Vite 8** -- Fast frontend build tool
- **Terraform** -- Infrastructure as Code engine (Intersight + Redfish providers)
- **Intersight Python SDK** -- Official SDK for Cisco Intersight API
- **51 Intersight resource mappers** -- Full coverage of all Easy IMM resource types for live sync
- **27 Redfish resource types** -- Comprehensive BMC management with live state reading

### Project Structure

```
EasyIMM-UCS-Toolkit/
├── run.sh                      # One-command start script
├── README.md                   # This file
├── .gitignore
├── domains/                    # Per-domain synced data (auto-created)
│   └── intersight.com/         # Example: synced from intersight.com
│       ├── organizations/
│       ├── pools/
│       ├── policies/
│       ├── profiles/
│       └── templates/
├── backend/
│   ├── requirements.txt        # Python dependencies
│   ├── app.py                  # FastAPI application
│   ├── schema_engine.py        # Easy IMM schema parser
│   ├── yaml_manager.py         # YAML file manager (local + domain merge)
│   ├── terraform_runner.py     # Terraform subprocess runner
│   ├── redfish_manager.py      # 27 Redfish resource schemas + TF generator
│   ├── redfish_direct.py       # Direct Redfish push + live state reader
│   ├── intersight_client.py    # Intersight SDK client (full attribute pull)
│   ├── intersight_mapper.py    # 51 Intersight→YAML resource mappers
│   ├── intersight_sync.py      # Background sync engine (per-domain)
│   ├── docascode_exporter.py   # CiscoIQ export mapper
│   └── static/                 # Built frontend (auto-generated)
├── frontend/
│   ├── package.json            # npm dependencies
│   ├── vite.config.js          # Vite build configuration
│   ├── src/
│   │   ├── App.jsx             # Main application
│   │   ├── api.js              # API client
│   │   ├── theme.js            # MUI dark theme
│   │   └── components/         # React components
│   └── public/                 # Static assets
└── redfish-workspace/          # Generated Redfish TF files (runtime)
```

---

## Features at a Glance

### Easy IMM Tab
- Organization management (create, delete, clone)
- Dynamic form editor for 50+ resource types (pools, policies, profiles, templates)
- Schema-validated fields with dropdowns, toggles, and cross-references
- Resource cloning across organizations
- **Intersight Live Sync** -- pull all deployed configs into per-domain folders with one click
- **Editable synced orgs** -- synced organizations show all categories with Add buttons, so you can create new resources even for orgs with no existing Intersight configuration
- **Unsync** -- remove synced domain data to clean up the tree
- Import from Intersight (browse mode)
- Terraform Init / Validate / Plan / Apply / Destroy with live output

### Redfish Tab
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
- **Live state sync** -- read the current BMC configuration with one click; green dots show which resources have live data; "Load Live Values" populates forms with actual server values
- **Two deployment methods:**
  - **Direct Push** -- PATCH/POST directly to BMC Redfish API (no Terraform needed, instant apply)
  - **Terraform IaC** -- Generate `.tf` files, plan, and apply with state management
- Independent Terraform runner for Redfish workspace

### Sync / Unsync
- **Sync** pulls live Intersight configurations into `domains/<fqdn>/` folders
- Each domain gets the full Easy IMM directory structure (organizations, pools, policies, profiles, templates)
- 51 resource type mappers cover all pools, policies, profiles, and templates
- **Hierarchical tree display**: Synced resources appear in a separate green "Synced from Intersight" section, grouped by domain name, then by organization name -- clearly separated from local configuration
- **MOID → name resolution**: Organization MOIDs are automatically resolved to their human-readable names (e.g., `CBUCSX-CBUAL.GOV.AE (6791c3a6…)` instead of raw `6791c3a66972653001fd82ff`)
- Local resources are never overwritten -- synced data lives in separate folders
- **Add to synced orgs**: All four categories (Pools, Policies, Profiles, Templates) are always visible for synced organizations, with Add buttons enabled -- so you can create new resources for orgs that have no existing configuration on Intersight
- **Unsync** removes a domain folder entirely, cleaning the tree instantly
- Also handles **legacy synced data** -- MOID-named organizations from older syncs that were stored directly in the main YAML files can be detected and removed
- Multiple domains can be synced simultaneously

### Export
- CiscoIQ Document-as-Code export (`data.tech-shared.yaml`, `data.tech-ucs.yaml`)
- YAML preview before download
- Maps hardware inventory, cabling, pools, policies, profiles, and administration settings

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
| Synced resources not appearing | Click the Refresh button after sync completes. Synced resources appear under the green "Synced from Intersight" section at the bottom of the tree. |
| Org names show as MOIDs | Ensure Intersight credentials are configured. The tree resolves MOIDs to names when a connection is active. |
| Unsync shows "No synced domains" | No `domains/` folders or legacy MOID organizations were found. Check if data was already unsynced. |
| Redfish live sync fails | Verify BMC endpoint, credentials, and that the server is reachable. The sync icon is disabled until a connection is saved. |
| Redfish shows "BMC connection not configured" | Save the BMC connection first (endpoint + username + password) before clicking the sync icon |

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
