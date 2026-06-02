"""
Centralised path configuration for the EasyIMM UCS Toolkit.

The Easy IMM workspace root can be set via the EASYIMM_ROOT environment
variable.  When unset it defaults to the parent of the app directory
(i.e. one level above ``Frontend-app/``).
"""

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent          # Frontend-app/
_default_root = APP_DIR.parent                            # one level up

EASYIMM_ROOT = Path(os.environ.get("EASYIMM_ROOT", str(_default_root)))
DOMAINS_ROOT = EASYIMM_ROOT / "domains"
REDFISH_WORKSPACE = APP_DIR / "redfish-workspace"
