# EasyIMM UCS Toolkit

A unified web-based configuration tool for Cisco UCS infrastructure. Manage Intersight Managed Mode (IMM) policies, Redfish bare-metal servers, and export documentation -- all from a single interface with built-in Terraform IaC deployment.

---

## What Is This?

EasyIMM UCS Toolkit is a browser-based application that provides a visual interface for configuring Cisco UCS infrastructure. It wraps two powerful Terraform ecosystems into one tool:

- **Easy IMM** -- The community [Easy IMM](https://github.com/terraform-cisco-modules/easy-imm) Terraform module framework for Cisco Intersight Managed Mode. Manage organizations, pools, policies, profiles, and templates through interactive forms instead of editing YAML files manually.

- **Redfish / ai-pods** -- Terraform-based configuration for bare-metal servers managed via the Redfish API (e.g., Cisco C885A AI infrastructure nodes). Configure BIOS, boot order, power state, BMC settings, and more through a guided UI.

Both tabs include integrated Terraform runners that let you validate, plan, apply, and destroy infrastructure directly from the browser.

---

## What Problem Does This Solve?

Configuring Cisco UCS infrastructure today requires:

1. **Deep Terraform/YAML knowledge** -- Easy IMM uses complex nested YAML schemas. A single typo can break an entire plan.
2. **Multiple disconnected tools** -- Intersight portal for cloud-managed servers, manual Redfish API calls for bare-metal, separate Terraform workspaces for each.
3. **No visual validation** -- You only discover errors at `terraform plan` time, often after editing dozens of files.
4. **Documentation gap** -- Design documents get out of sync with actual deployed configuration.

This toolkit solves all of these:

- **Visual forms with schema validation** -- Every field is rendered with the correct input type, default values, and validation rules derived from the Easy IMM JSON schema.
- **Unified interface** -- One tool for both Intersight-managed and Redfish-managed infrastructure.
- **Live Terraform integration** -- Init, plan, apply, and destroy from the UI with real-time streaming output.
- **Import from Intersight** -- Pull existing configurations from your Intersight account to see what's already deployed.
- **CiscoIQ Doc-as-Code export** -- Generate `data.tech-shared.yaml` and `data.tech-ucs.yaml` files that can be imported into the CiscoIQ platform for automated documentation.

---

## How Does It Work?

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Browser (React + MUI)              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │  Easy IMM    │  │  Redfish /   │  │  Export /  │  │
│  │  Config Tab  │  │  ai-pods Tab │  │  Import    │  │
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
│  │  docascode_exporter CiscoIQ YAML export     │     │
│  └──────────────┬──────────────────┬───────────┘     │
│                 │                  │                  │
│  ┌──────────────▼──┐  ┌───────────▼──────────┐      │
│  │  Easy IMM Root  │  │  Redfish Workspace   │      │
│  │  .ezi.yaml      │  │  .tf / .tfvars       │      │
│  │  Terraform HCL  │  │  config.json         │      │
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

2. **Redfish tab**: The UI presents configuration forms for Redfish resource types (BIOS, boot order, power, etc.). When you click "Generate TF", the backend creates Terraform files (`provider.tf`, `variables.tf`, `main.tf`, `terraform.tfvars`) in the Redfish workspace. Then Init/Plan/Apply deploys via the `ciscodevnet/redfish` Terraform provider.

3. **Import**: Connects to Cisco Intersight via the official Python SDK to fetch existing organizations, pools, policies, and profiles.

4. **Export**: Maps both Easy IMM and Redfish configurations into CiscoIQ Document-as-Code YAML format for automated documentation generation.

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
#    → http://localhost:8100
```

That's it. The `run.sh` script automatically:
- Detects and validates your Python installation
- Creates a virtual environment and installs dependencies
- Builds the frontend if not already built
- Starts the server on port 8100

### Configuration

**Intersight API credentials** (for Easy IMM tab):
1. Click the Settings (gear) icon in the toolbar
2. Enter your Intersight API Key ID
3. Enter the path to your `SecretKey.txt` file
4. Click Save

**Redfish BMC connection** (for Redfish tab):
1. Switch to the "Redfish / ai-pods" tab
2. Enter the BMC endpoint URL (e.g., `https://10.0.0.1`)
3. Enter username and password
4. Click Save Connection

### Commands

```bash
./run.sh              # Start in production mode (single port: 8100)
./run.sh dev          # Start in development mode (hot-reload, ports 3100 + 8100)
./run.sh build        # Build frontend without starting
./run.sh stop         # Stop background dev processes
PORT=9000 ./run.sh    # Start on a custom port
```

---

## Technical Construct

### Backend (Python / FastAPI)

| Module | Purpose |
|--------|---------|
| `app.py` | FastAPI application, REST + WebSocket endpoints, static file serving |
| `schema_engine.py` | Parses the Easy IMM JSON schema to generate dynamic form definitions |
| `yaml_manager.py` | CRUD operations on `.ezi.yaml` files organized by organization |
| `terraform_runner.py` | Async subprocess runner for Terraform commands with streaming output |
| `redfish_manager.py` | Redfish resource schemas, config storage, TF file generation |
| `intersight_client.py` | Intersight Python SDK wrapper for importing existing configs |
| `docascode_exporter.py` | Maps configs to CiscoIQ Document-as-Code YAML schema |

### Frontend (React + Vite + Material UI)

| Component | Purpose |
|-----------|---------|
| `App.jsx` | Main shell with tab navigation and toolbar |
| `TreeNavigator.jsx` | Hierarchical tree view of orgs/pools/policies/profiles |
| `ResourcePanel.jsx` | Dynamic form editor for any Easy IMM resource |
| `RedfishPanel.jsx` | Redfish server configuration with master-detail layout |
| `TerraformPanel.jsx` | Real-time Terraform command runner (Easy IMM) |
| `ImportDialog.jsx` | Multi-step import wizard for Intersight |
| `ExportDialog.jsx` | CiscoIQ Document-as-Code YAML preview and download |
| `SettingsDialog.jsx` | API key and connection settings |
| `CloneDialog.jsx` | Clone resources across organizations |

### Key Technologies

- **FastAPI** -- High-performance Python web framework with async support
- **WebSockets** -- Real-time streaming of Terraform command output
- **React 19** -- UI library with hooks-based architecture
- **Material UI 9** -- Component library for consistent, accessible UI
- **Vite 8** -- Fast frontend build tool
- **Terraform** -- Infrastructure as Code engine (Intersight + Redfish providers)
- **Intersight Python SDK** -- Official SDK for Cisco Intersight API

### Project Structure

```
EasyIMM-UCS-Toolkit/
├── run.sh                      # One-command start script
├── README.md                   # This file
├── .gitignore
├── backend/
│   ├── requirements.txt        # Python dependencies
│   ├── app.py                  # FastAPI application
│   ├── schema_engine.py        # Easy IMM schema parser
│   ├── yaml_manager.py         # YAML file manager
│   ├── terraform_runner.py     # Terraform subprocess runner
│   ├── redfish_manager.py      # Redfish config + TF generator
│   ├── intersight_client.py    # Intersight SDK client
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
- Import existing configs from Cisco Intersight
- Terraform Init / Validate / Plan / Apply / Destroy with live output

### Redfish Tab
- BMC connection management (endpoint, credentials, TLS)
- 11 configurable resource types: BIOS, Boot Order, Power, BMC Settings, BMC Network Protocol, Virtual Media, Secure Boot, Identify LED, BIOS Reset, Event Subscriptions, Log Service
- Enable/disable individual resources
- Auto-generate Terraform files from UI configuration
- Independent Terraform runner for Redfish workspace

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
| Port 8100 already in use | Run with a different port: `PORT=9000 ./run.sh` |
| Intersight auth fails | Verify your API Key ID and SecretKey.txt path in Settings |
| Frontend not loading | Run `./run.sh build` to rebuild the frontend |

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
