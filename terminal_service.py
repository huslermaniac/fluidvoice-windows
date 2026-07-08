"""
terminal_service.py — FluidVoice Windows
Executes terminal/PowerShell commands on Windows for Command Mode agent.
Equivalent of TerminalService.swift on macOS.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any


class TerminalService:
    """Executes shell commands on Windows (using PowerShell)."""

    @property
    def tool_definition(self) -> dict[str, Any]:
        """Returns the function definition in OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": "execute_terminal_command",
                "description": (
                    "Execute a command line utility / script in PowerShell on the user's Windows computer.\n"
                    "Use this for file operations (dir, type, mkdir, del), git commands, winget, pip, python, "
                    "or launching applications (e.g. Start-Process notepad).\n\n"
                    "IMPORTANT: Follow the agentic workflow:\n"
                    "1. ALWAYS check prerequisites first (file exists, folder exists, command available)\n"
                    "2. Execute the main action\n"
                    "3. Verify the result\n\n"
                    "Returns JSON with: success (bool), output (stdout), error (stderr), exitCode, executionTimeMs."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The PowerShell command to execute (e.g., 'Get-ChildItem', 'cat file.txt', 'Start-Process notepad')"
                        },
                        "workingDirectory": {
                            "type": "string",
                            "description": "Optional working directory. Defaults to the user's home directory."
                        },
                        "purpose": {
                            "type": "string",
                            "description": (
                                "Brief description of why this command is being run. Must be one of:\n"
                                "- 'checking' (verifying prerequisites)\n"
                                "- 'executing' (main action)\n"
                                "- 'verifying' (confirming result)\n"
                                "Example: 'Checking if config.json exists'"
                            )
                        }
                    },
                    "required": ["command", "purpose"]
                }
            }
        }

    def execute(
        self,
        command: str,
        working_directory: str | None = None,
        timeout: float = 30.0
    ) -> dict[str, Any]:
        """Execute a PowerShell command and return a diagnostic result dict."""
        start_time = time.time()
        
        # Determine working directory
        cwd = working_directory
        if not cwd or not os.path.exists(cwd):
            cwd = os.path.expanduser("~")

        # Run command in PowerShell
        # -NoProfile prevents loading user profiles for faster startup
        # -Command runs the specified script/command
        shell_args = ["powershell.exe", "-NoProfile", "-Command", command]

        try:
            res = subprocess.run(
                shell_args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace"
            )
            elapsed = int((time.time() - start_time) * 1000)
            
            return {
                "success": res.returncode == 0,
                "command": command,
                "output": res.stdout.strip(),
                "error": res.stderr.strip() if res.stderr.strip() else None,
                "exitCode": res.returncode,
                "executionTimeMs": elapsed
            }
        except subprocess.TimeoutExpired:
            elapsed = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "command": command,
                "output": "",
                "error": f"Command timed out after {timeout} seconds",
                "exitCode": -2,
                "executionTimeMs": elapsed
            }
        except Exception as e:
            elapsed = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "command": command,
                "output": "",
                "error": str(e),
                "exitCode": -1,
                "executionTimeMs": elapsed
            }
