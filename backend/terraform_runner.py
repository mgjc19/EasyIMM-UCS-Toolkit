"""
Terraform Runner -- executes terraform commands and streams output.
"""

import asyncio
import os
import re
from pathlib import Path

EASYIMM_ROOT = Path(__file__).resolve().parent.parent.parent
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


class TerraformRunner:
    def __init__(self, root: str | None = None):
        self.root = Path(root) if root else EASYIMM_ROOT
        self._process = None

    def _env(self) -> dict:
        env = os.environ.copy()
        env_sh = self.root / "env.sh"
        if env_sh.exists():
            with open(env_sh) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("export ") and "=" in line:
                        kv = line[7:]
                        key, _, val = kv.partition("=")
                        val = val.strip("'\"")
                        if key and val:
                            env[key] = val
        return env

    async def run(self, command: str, callback=None) -> dict:
        args_map = {
            "init": ["terraform", "init"],
            "validate": ["terraform", "validate"],
            "plan": ["terraform", "plan", "-out=main.plan", "-no-color"],
            "apply": ["terraform", "apply", "-auto-approve", "main.plan", "-no-color"],
            "destroy": ["terraform", "destroy", "-auto-approve", "-no-color"],
            "state_list": ["terraform", "state", "list"],
        }

        args = args_map.get(command)
        if not args:
            return {"success": False, "output": f"Unknown command: {command}"}

        env = self._env()
        output_lines = []

        try:
            self._process = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(self.root),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            async for line_bytes in self._process.stdout:
                line = line_bytes.decode("utf-8", errors="replace")
                clean_line = ANSI_ESCAPE.sub("", line)
                output_lines.append(clean_line)
                if callback:
                    await callback(clean_line)

            await self._process.wait()
            return {
                "success": self._process.returncode == 0,
                "exit_code": self._process.returncode,
                "output": "".join(output_lines),
            }
        except FileNotFoundError:
            return {"success": False, "output": "terraform not found. Is it installed?"}
        except Exception as exc:
            return {"success": False, "output": str(exc)}
        finally:
            self._process = None

    async def cancel(self):
        if self._process:
            self._process.terminate()
