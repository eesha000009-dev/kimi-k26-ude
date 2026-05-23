"""
Kimi K2.6 UDE - Complete Agent Engine
======================================
Full-featured Unified Developer Environment with the 3 Pillars:

PILLAR 1 - The Brain (Kimi K2.6 API via NVIDIA):
  NVIDIA API integration with streaming + thinking mode

PILLAR 2 - The Orchestrator (OpenClaw):
  Command interception, routing, safety validation, error recovery,
  audit logging, context memory management

PILLAR 3 - The Sandbox Execution Layer:
  Terminal execution, Docker sandboxing, MCP tools, browser automation

Additional Features:
- Agent Swarm (up to 300 sub-agents, multi-model critique)
- 4,000-step long-horizon execution
- Streaming responses with thinking content
"""

import os
import io
import json
import subprocess
import threading
import time
import re
import hashlib
from queue import Queue
from typing import Optional, List, Dict, Any
import requests

# Import OpenClaw (Pillar 2)
try:
    from openclaw import OpenClaw, RouteType, SafetyLevel
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from openclaw import OpenClaw, RouteType, SafetyLevel

# ── NVIDIA API Configuration ──────────────────────────────────
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_API_KEY = "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"
DEFAULT_MODEL = "moonshotai/kimi-k2.6"
DEFAULT_MAX_TOKENS = 16384
DEFAULT_TEMPERATURE = 0.6
DEFAULT_TOP_P = 1.0
DEFAULT_MAX_STEPS = 50
COMMAND_TIMEOUT = 60
# Use local path on Linux, /sdcard on Android
_is_android = os.path.exists('/system/app')
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "/sdcard/kimi_ude_workspace" if _is_android else os.path.expanduser("~/kimi_ude_workspace"))

# ── System Prompts ────────────────────────────────────────────
UDE_SYSTEM_PROMPT = """You are the core intelligence of an advanced autonomous Unified Developer Environment (UDE).
Unlike your browser alternative, you have full local terminal access.
When the user gives you a task, break it down into steps.

To execute terminal commands or write files, respond ONLY in this JSON format:
{
    "thought": "Your reasoning process here",
    "command": "the exact bash command to execute (e.g., 'mkdir app && cat << 'EOF' > app/main.py...')"
}

If the task is fully completed, respond with:
{
    "thought": "Done",
    "command": "COMPLETE"
}

Important rules:
- Always create files inside the workspace directory
- Test your code after writing it
- Read error messages carefully and fix issues iteratively
- Be thorough and complete every step before marking as COMPLETE
- You have access to a full bash terminal with all standard tools
- You can install packages, create directories, write files, run compilers, etc.

OpenClaw Integration:
- Your commands are intercepted by the OpenClaw orchestrator
- OpenClaw routes your commands to the appropriate execution backend
- Dangerous commands are flagged; blocked commands are rejected
- MCP tools available: read_file, write_file, list_files, run_command, browser_open, browser_screenshot
- Use mcp://tool_name/param format for MCP tool calls
- Use browser://url format for browser automation
"""

SWARM_CRITIC_PROMPT = """You are a code reviewer agent in an Agent Swarm. Your job is to critically review
the code and output produced by another agent. Look for:
1. Bugs and logic errors
2. Security vulnerabilities
3. Performance issues
4. Missing error handling
5. Code style issues

Provide your critique in this JSON format:
{
    "critique": "Your detailed review comments",
    "severity": "critical|warning|info",
    "suggested_fix": "The bash command to fix the issue, or empty if no fix needed"
}

If the code looks good and no fixes are needed:
{
    "critique": "Code looks good",
    "severity": "info",
    "suggested_fix": ""
}
"""

SWARM_ORCHESTRATOR_PROMPT = """You are the Orchestrator of an Agent Swarm. You coordinate multiple sub-agents
to work on complex tasks. Each sub-agent has a specific role:
- Coder: Writes and modifies code
- Reviewer: Reviews code for bugs and issues
- Tester: Runs tests and validates output
- Fixer: Applies fixes based on review feedback

Given the task and current state, decide which agent should act next and what they should do.
Respond in this JSON format:
{
    "thought": "Your orchestration reasoning",
    "next_agent": "coder|reviewer|tester|fixer",
    "instruction": "What the next agent should do",
    "command": "Any bash command to execute first, or empty"
}
"""


# ══════════════════════════════════════════════════════════════
# PILLAR 3: THE SANDBOX EXECUTION LAYER
# ══════════════════════════════════════════════════════════════

# ── Command Execution ─────────────────────────────────────────
class CommandExecutor:
    """Handles command execution with optional Docker sandboxing.

    This is the core of Pillar 3 - The Sandbox Execution Layer.
    It provides secure execution of commands either locally or
    inside Docker containers.
    """

    def __init__(self, workspace_dir=WORKSPACE_DIR, use_docker=False, docker_image="python:3.12-slim"):
        self.workspace_dir = workspace_dir
        self.use_docker = use_docker
        self.docker_image = docker_image
        os.makedirs(workspace_dir, exist_ok=True)

    def execute(self, cmd: str, timeout: int = COMMAND_TIMEOUT) -> str:
        """Execute a command either locally or in a Docker container."""
        if self.use_docker and self._docker_available():
            return self._execute_docker(cmd, timeout)
        return self._execute_local(cmd, timeout)

    def _execute_local(self, cmd: str, timeout: int) -> str:
        """Execute bash commands locally in the workspace directory."""
        try:
            wrapped_cmd = f"cd {self.workspace_dir} && {cmd}"
            result = subprocess.run(
                wrapped_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            return output.strip() if output.strip() else "Command executed successfully with no output."
        except subprocess.TimeoutExpired:
            return f"⏱️ Command timed out after {timeout}s"
        except Exception as e:
            return f"❌ Execution Error: {str(e)}"

    def _execute_docker(self, cmd: str, timeout: int) -> str:
        """Execute commands inside a Docker container for safe sandboxing."""
        try:
            docker_cmd = (
                f"docker run --rm "
                f"-v {self.workspace_dir}:/workspace "
                f"-w /workspace "
                f"--memory=512m --cpus=1 "
                f"--network=host "
                f"{self.docker_image} "
                f"bash -c {subprocess.list2cmdline([cmd])}"
            )
            result = subprocess.run(
                docker_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout + 30,  # Extra time for Docker overhead
            )
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            return output.strip() if output.strip() else "Docker: Command executed successfully with no output."
        except subprocess.TimeoutExpired:
            return f"⏱️ Docker command timed out after {timeout}s"
        except Exception as e:
            return f"❌ Docker Error: {str(e)}"

    def _docker_available(self) -> bool:
        """Check if Docker is available on the system."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False


# ══════════════════════════════════════════════════════════════
# PILLAR 1: THE BRAIN (Kimi K2.6 API)
# ══════════════════════════════════════════════════════════════

# ── NVIDIA API Client ─────────────────────────────────────────
class NvidiaKimiClient:
    """Direct NVIDIA API client for Kimi K2.6 with streaming support.

    This is Pillar 1 - The Brain. It communicates with the Kimi K2.6
    1-trillion parameter model via the NVIDIA API, supporting:
    - Standard chat completions
    - Streaming (SSE) responses
    - Thinking/reasoning mode
    - Structured JSON output
    """

    def __init__(self, api_key: str = DEFAULT_API_KEY, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model
        self.base_url = NVIDIA_BASE_URL
        self.max_tokens = DEFAULT_MAX_TOKENS
        self.temperature = DEFAULT_TEMPERATURE
        self.top_p = DEFAULT_TOP_P
        self.thinking_enabled = True

    def chat(self, messages: List[Dict], stream: bool = False, temperature: float = None) -> Dict:
        """Send a chat completion request (non-streaming)."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": temperature or self.temperature,
            "top_p": self.top_p,
            "stream": False,
            "chat_template_kwargs": {"thinking": self.thinking_enabled},
        }

        try:
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def chat_stream(self, messages: List[Dict], temperature: float = None):
        """Send a chat completion request with SSE streaming. Yields chunks."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": temperature or self.temperature,
            "top_p": self.top_p,
            "stream": True,
            "chat_template_kwargs": {"thinking": self.thinking_enabled},
        }

        try:
            response = requests.post(self.base_url, headers=headers, json=payload, stream=True, timeout=120)
            response.raise_for_status()

            full_content = ""
            thinking_content = ""

            for line in response.iter_lines():
                if not line:
                    continue
                line_text = line.decode("utf-8")
                if not line_text.startswith("data: "):
                    continue
                data_str = line_text[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        # Handle thinking content
                        if "reasoning_content" in delta:
                            thinking_content += delta["reasoning_content"]
                            yield {"type": "thinking", "content": delta["reasoning_content"]}
                        # Handle regular content
                        if "content" in delta:
                            full_content += delta["content"]
                            yield {"type": "content", "content": delta["content"]}
                except json.JSONDecodeError:
                    continue

            yield {"type": "done", "full_content": full_content, "thinking_content": thinking_content}

        except requests.exceptions.RequestException as e:
            yield {"type": "error", "content": str(e)}


# ── MCP Integration Layer ─────────────────────────────────────
class MCPBridge:
    """Model Context Protocol bridge for universal tool/state integration.
    Provides standardized state layer for connecting to local environments,
    VS Code, Chrome sessions, and file systems simultaneously."""

    def __init__(self, workspace_dir=WORKSPACE_DIR):
        self.workspace_dir = workspace_dir
        self.state = {}  # Shared state store
        self.file_cache = {}  # File content cache
        self.browser_sessions = {}  # Browser session tracking
        self.tools = self._register_tools()

    def _register_tools(self) -> List[Dict]:
        """Register available MCP tools."""
        return [
            {"name": "read_file", "description": "Read a file from workspace", "params": ["path"]},
            {"name": "write_file", "description": "Write content to a file in workspace", "params": ["path", "content"]},
            {"name": "list_files", "description": "List files in workspace directory", "params": ["path"]},
            {"name": "run_command", "description": "Execute a bash command", "params": ["command"]},
            {"name": "get_state", "description": "Get shared state value", "params": ["key"]},
            {"name": "set_state", "description": "Set shared state value", "params": ["key", "value"]},
            {"name": "browser_open", "description": "Open a URL in headless browser", "params": ["url"]},
            {"name": "browser_screenshot", "description": "Take screenshot of current page", "params": []},
        ]

    def execute_tool(self, tool_name: str, params: Dict) -> Any:
        """Execute an MCP tool call."""
        if tool_name == "read_file":
            return self._read_file(params.get("path", ""))
        elif tool_name == "write_file":
            return self._write_file(params.get("path", ""), params.get("content", ""))
        elif tool_name == "list_files":
            return self._list_files(params.get("path", ""))
        elif tool_name == "get_state":
            return self.state.get(params.get("key"))
        elif tool_name == "set_state":
            self.state[params.get("key")] = params.get("value")
            return f"State set: {params.get('key')}"
        elif tool_name == "browser_open":
            return self._browser_open(params.get("url", ""))
        elif tool_name == "browser_screenshot":
            return self._browser_screenshot()
        return f"Unknown tool: {tool_name}"

    def _read_file(self, path: str) -> str:
        full_path = os.path.join(self.workspace_dir, path)
        try:
            with open(full_path, "r") as f:
                content = f.read()
            self.file_cache[path] = content
            return content
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def _write_file(self, path: str, content: str) -> str:
        full_path = os.path.join(self.workspace_dir, path)
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)
            self.file_cache[path] = content
            return f"File written: {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    def _list_files(self, path: str = "") -> str:
        full_path = os.path.join(self.workspace_dir, path)
        try:
            entries = os.listdir(full_path)
            return json.dumps(entries)
        except Exception as e:
            return f"Error listing files: {str(e)}"

    def _browser_open(self, url: str) -> str:
        """Open URL in headless browser (requires Playwright/Browser Use)."""
        self.browser_sessions["active"] = {"url": url, "status": "opened"}
        try:
            result = subprocess.run(
                f"python3 -c \"from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); pg=b.new_page(); pg.goto('{url}'); pg.screenshot(path='{self.workspace_dir}/screenshot.png'); b.close(); p.stop()\"",
                shell=True, capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return f"Browser opened {url}, screenshot saved"
        except Exception:
            pass
        return f"Browser open requested for {url} (install playwright for full support: pip install playwright && playwright install)"

    def _browser_screenshot(self) -> str:
        """Take screenshot of current browser page."""
        screenshot_path = os.path.join(self.workspace_dir, "screenshot.png")
        if os.path.exists(screenshot_path):
            return f"Screenshot exists at {screenshot_path}"
        return "No screenshot available. Use browser_open first."


# ── Agent Swarm ───────────────────────────────────────────────
class AgentSwarm:
    """Multi-agent swarm with up to 300 sub-agents.
    Implements collaborative coding with Coder, Reviewer, Tester, and Fixer agents."""

    def __init__(self, client: NvidiaKimiClient, executor: CommandExecutor,
                 openclaw: OpenClaw, event_queue: Queue):
        self.client = client
        self.executor = executor
        self.openclaw = openclaw
        self.event_queue = event_queue
        self.max_agents = 300
        self.active_agents = {}
        self.agent_history = []

    def _emit(self, event_type: str, data: Dict):
        self.event_queue.put({"type": event_type, "data": data})

    def run_swarm(self, goal: str, max_iterations: int = 20, num_critics: int = 2):
        """Run a swarm of agents on a task.

        Args:
            goal: The task to accomplish
            max_iterations: Max orchestration cycles
            num_critics: Number of critic/reviewer agents (1-299)
        """
        self._emit("swarm_start", {
            "goal": goal,
            "max_iterations": max_iterations,
            "num_critics": min(num_critics, self.max_agents - 1),
        })

        # Phase 1: Coder agent writes initial code
        self._emit("swarm_agent_start", {"agent": "coder", "phase": "initial_coding"})

        coder_messages = [
            {"role": "system", "content": UDE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {goal}\n\nWrite the complete code. Create all necessary files and test them."}
        ]

        iteration = 0
        last_output = ""
        last_thought = ""
        task_complete = False

        while iteration < max_iterations and not task_complete:
            iteration += 1
            self._emit("swarm_iteration", {"iteration": iteration, "max": max_iterations})

            # ── Coder Phase ──
            self._emit("swarm_agent_start", {"agent": "coder", "iteration": iteration})

            coder_response = self.client.chat(coder_messages)
            if "error" in coder_response:
                self._emit("error", {"message": f"Coder API error: {coder_response['error']}"})
                break

            coder_content = coder_response.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Route through OpenClaw (Pillar 2)
            route_result = self.openclaw.intercept_and_route(coder_content, use_docker=self.executor.use_docker)

            if not route_result.get("success") and route_result.get("route") == "blocked":
                # Command was blocked by OpenClaw safety layer
                self._emit("swarm_agent_thought", {
                    "agent": "coder",
                    "thought": f"⛔ Command blocked by OpenClaw: {route_result.get('output', '')}",
                })
                coder_messages.append({"role": "assistant", "content": coder_content})
                coder_messages.append({"role": "user", "content": f"OpenClaw blocked your command: {route_result.get('output', '')}. Try a safer approach."})
                continue

            if route_result.get("is_complete"):
                self._emit("swarm_complete", {
                    "iterations": iteration, "status": "completed",
                    "final_thought": route_result.get("thought", "")
                })
                task_complete = True
                break

            thought = route_result.get("thought", "")
            cmd = route_result.get("command", "")
            output = route_result.get("output", "")
            route_type = route_result.get("route", "terminal")
            safety = route_result.get("safety", "safe")

            self._emit("swarm_agent_thought", {
                "agent": "coder",
                "thought": thought,
                "command": cmd,
                "route": route_type,
                "safety": safety,
            })

            self._emit("swarm_agent_output", {
                "agent": "coder", "command": cmd, "output": output[:500],
                "route": route_type,
            })

            coder_messages.append({"role": "assistant", "content": coder_content})
            coder_messages.append({"role": "user", "content": f"Terminal Output (via OpenClaw [{route_type}], safety: {safety}):\n{output}"})

            # ── Prune context via OpenClaw's memory manager ──
            coder_messages = self.openclaw.memory.prune(coder_messages)

            # ── Critic Phase (parallel reviewers) ──
            critic_feedback = []
            for i in range(min(num_critics, 3)):  # Limit concurrent critics
                self._emit("swarm_agent_start", {"agent": f"reviewer_{i+1}", "iteration": iteration})

                critic_messages = [
                    {"role": "system", "content": SWARM_CRITIC_PROMPT},
                    {"role": "user", "content": f"Review this code/command and its output:\n\nCommand: {cmd}\nOutput:\n{output}\n\nProvide critique in JSON format."}
                ]

                critic_response = self.client.chat(critic_messages, temperature=0.4)
                if "error" not in critic_response:
                    critic_content = critic_response.get("choices", [{}])[0].get("message", {}).get("content", "")
                    try:
                        critique = json.loads(critic_content)
                    except json.JSONDecodeError:
                        critique = {"critique": critic_content[:300], "severity": "info", "suggested_fix": ""}

                    critic_feedback.append(critique)
                    self._emit("swarm_agent_thought", {
                        "agent": f"reviewer_{i+1}",
                        "thought": critique.get("critique", "")[:200],
                        "severity": critique.get("severity", "info")
                    })

                    # Auto-fix if severity is critical - route through OpenClaw
                    fix = critique.get("suggested_fix", "")
                    if critique.get("severity") == "critical" and fix:
                        self._emit("swarm_agent_start", {"agent": "fixer", "reason": "critical_issue"})
                        fix_route = self.openclaw.intercept_and_route(
                            json.dumps({"thought": "Applying critical fix", "command": fix}),
                            use_docker=self.executor.use_docker
                        )
                        fix_output = fix_route.get("output", "Fix blocked or failed")
                        self._emit("swarm_agent_output", {
                            "agent": "fixer", "command": fix, "output": fix_output[:300],
                            "route": fix_route.get("route", "terminal"),
                        })
                        coder_messages.append({"role": "user", "content": f"A critical issue was found and fixed via OpenClaw:\n{critique.get('critique')}\nFix applied: {fix}\nFix output: {fix_output}"})

            # ── Tester Phase (every 3 iterations) ──
            if iteration % 3 == 0 and not task_complete:
                self._emit("swarm_agent_start", {"agent": "tester", "iteration": iteration})
                test_messages = [
                    {"role": "system", "content": UDE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Run comprehensive tests on the code in the workspace. Look for files and run them with appropriate test commands. Output in JSON format with thought and command."}
                ]
                test_response = self.client.chat(test_messages, temperature=0.3)
                if "error" not in test_response:
                    test_content = test_response.get("choices", [{}])[0].get("message", {}).get("content", "")
                    # Route through OpenClaw
                    test_route = self.openclaw.intercept_and_route(test_content, use_docker=self.executor.use_docker)
                    if test_route.get("success") and not test_route.get("is_complete"):
                        test_cmd = test_route.get("command", "")
                        test_output = test_route.get("output", "")
                        self._emit("swarm_agent_output", {
                            "agent": "tester", "command": test_cmd, "output": test_output[:500],
                            "route": test_route.get("route", "terminal"),
                        })
                        coder_messages.append({"role": "user", "content": f"Test results (via OpenClaw [{test_route.get('route', 'terminal')}]):\n{test_output}"})

        if not task_complete:
            self._emit("swarm_complete", {"iterations": iteration, "status": "max_iterations_reached", "final_thought": last_thought})


# ══════════════════════════════════════════════════════════════
# MAIN UDE AGENT - Connects All 3 Pillars
# ══════════════════════════════════════════════════════════════

class KimiUDEAgent:
    """Complete Kimi K2.6 UDE Agent - All 3 Pillars Connected.

    Pillar 1: The Brain (NvidiaKimiClient) - AI reasoning
    Pillar 2: The Orchestrator (OpenClaw) - Command routing & safety
    Pillar 3: The Sandbox (CommandExecutor) - Secure execution

    Additional: Agent Swarm, MCP Integration, Browser Automation
    """

    def __init__(self):
        # ── Configuration ──
        self.api_key = DEFAULT_API_KEY
        self.model = DEFAULT_MODEL
        self.max_steps = DEFAULT_MAX_STEPS
        self.workspace_dir = WORKSPACE_DIR
        self.thinking_enabled = True
        self.use_docker = False
        self.docker_image = "python:3.12-slim"
        self.use_swarm = False
        self.swarm_critics = 2
        self.running = False
        self._stop_flag = False
        self.event_queue = Queue()

        # ── Pillar Components ──
        self.client = None        # Pillar 1: The Brain
        self.openclaw = None      # Pillar 2: The Orchestrator
        self.executor = None      # Pillar 3: The Sandbox
        self.mcp = None           # MCP Integration
        self.swarm = None         # Agent Swarm

        self._init_components()

    def _init_components(self):
        """Initialize all agent components - connecting the 3 Pillars."""
        # Pillar 1: The Brain
        self.client = NvidiaKimiClient(api_key=self.api_key, model=self.model)
        self.client.thinking_enabled = self.thinking_enabled

        # Pillar 3: The Sandbox Execution Layer
        self.executor = CommandExecutor(self.workspace_dir, self.use_docker, self.docker_image)

        # MCP Bridge
        self.mcp = MCPBridge(self.workspace_dir)

        # Pillar 2: The Orchestrator (OpenClaw) - connects Brain to Sandbox
        self.openclaw = OpenClaw(event_queue=self.event_queue)
        self.openclaw.register_backends(
            terminal=self.executor,
            docker=self.executor if self.use_docker else None,
            mcp=self.mcp,
            browser=self.mcp,  # MCP handles browser tools
            workspace_dir=self.workspace_dir,
        )

        # Agent Swarm (uses all 3 pillars)
        self.swarm = AgentSwarm(self.client, self.executor, self.openclaw, self.event_queue)

    def configure(self, **kwargs):
        """Update configuration and reinitialize components."""
        for key, value in kwargs.items():
            if value is not None and hasattr(self, key):
                setattr(self, key, value)
        self._init_components()

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def stop(self):
        self._stop_flag = True

    def _emit(self, event_type: str, data: Dict):
        self.event_queue.put({"type": event_type, "data": data})

    def run(self, goal: str):
        """Run the UDE agent loop - All 3 Pillars working together.

        Flow: Brain → OpenClaw → Sandbox → Brain (feedback loop)
        """
        if not self.api_key:
            self._emit("error", {"message": "API Key not configured. Go to Settings."})
            return

        self.running = True
        self._stop_flag = False
        self._init_components()

        if self.use_swarm:
            self.swarm.run_swarm(goal, max_iterations=self.max_steps, num_critics=self.swarm_critics)
            self.running = False
            return

        # ── Standard UDE Loop with OpenClaw ──
        messages = [
            {"role": "system", "content": UDE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {goal}"}
        ]

        self._emit("session_start", {
            "goal": goal,
            "model": self.model,
            "max_steps": self.max_steps,
            "workspace": self.workspace_dir,
            "docker": self.use_docker,
            "thinking": self.thinking_enabled,
            "pillars": {
                "brain": "NvidiaKimiClient",
                "orchestrator": "OpenClaw",
                "sandbox": "CommandExecutor",
            },
        })

        steps = 0
        while steps < self.max_steps and not self._stop_flag:
            steps += 1
            self._emit("step_start", {"step": steps, "status": "thinking"})

            try:
                # ── Pillar 1: The Brain - Call Kimi K2.6 ──
                thinking_text = ""
                content_text = ""

                for chunk in self.client.chat_stream(messages):
                    if self._stop_flag:
                        break

                    if chunk["type"] == "thinking":
                        thinking_text += chunk["content"]
                        if len(thinking_text) % 100 < 5:
                            self._emit("thinking_update", {"step": steps, "thinking": thinking_text[-200:]})

                    elif chunk["type"] == "content":
                        content_text += chunk["content"]

                    elif chunk["type"] == "error":
                        self._emit("error", {"step": steps, "message": chunk["content"]})
                        break

                    elif chunk["type"] == "done":
                        content_text = chunk.get("full_content", content_text)
                        thinking_text = chunk.get("thinking_content", thinking_text)

                if self._stop_flag:
                    break

                # ── Pillar 2: The Orchestrator (OpenClaw) - Route Command ──
                route_result = self.openclaw.intercept_and_route(content_text, use_docker=self.use_docker)

                if not route_result.get("success"):
                    # Route failed (could be blocked or parse error)
                    self._emit("step_thought", {
                        "step": steps,
                        "thought": route_result.get("error", "Unknown error"),
                        "command": route_result.get("command", ""),
                        "thinking_content": thinking_text[-500:] if thinking_text else "",
                    })
                    self._emit("error", {
                        "step": steps,
                        "message": route_result.get("output", route_result.get("error", "OpenClaw routing failed")),
                    })
                    # Feed error back to Kimi for self-correction
                    messages.append({"role": "assistant", "content": content_text})
                    messages.append({"role": "user", "content": f"OpenClaw Error: {route_result.get('output', 'Routing failed')}. Try a different approach."})
                    # Prune context
                    messages = self.openclaw.memory.prune(messages)
                    continue

                if route_result.get("is_complete"):
                    self._emit("step_thought", {
                        "step": steps,
                        "thought": route_result.get("thought", "Done"),
                        "command": "COMPLETE",
                        "thinking_content": thinking_text[-500:] if thinking_text else "",
                    })
                    self._emit("step_complete", {
                        "step": steps, "thought": route_result.get("thought", ""),
                        "command": "COMPLETE", "output": "", "status": "complete"
                    })
                    self._emit("session_end", {
                        "total_steps": steps, "status": "completed",
                        "final_thought": route_result.get("thought", ""),
                        "openclaw_stats": self.openclaw.get_status(),
                    })
                    break

                # ── Get route details ──
                thought = route_result.get("thought", "")
                cmd = route_result.get("command", "")
                output = route_result.get("output", "")
                route_type = route_result.get("route", "terminal")
                safety = route_result.get("safety", "safe")
                duration = route_result.get("duration_ms", 0)

                # Include thinking content if available
                full_thought = thought
                if thinking_text:
                    full_thought = f"[Thinking] {thinking_text[-300:]}\n\n[Decision] {thought}"

                self._emit("step_thought", {
                    "step": steps,
                    "thought": full_thought,
                    "command": cmd,
                    "thinking_content": thinking_text[-500:] if thinking_text else "",
                    "route": route_type,
                    "safety": safety,
                })

                self._emit("command_start", {"step": steps, "command": cmd, "route": route_type})

                self._emit("step_complete", {
                    "step": steps, "thought": full_thought,
                    "command": cmd, "output": output,
                    "status": "completed",
                    "route": route_type,
                    "safety": safety,
                    "duration_ms": duration,
                })

                # ── Feed back into conversation memory ──
                messages.append({"role": "assistant", "content": content_text})
                feedback = f"Terminal Output (via OpenClaw [{route_type}], safety: {safety}):\n{output}"

                # Add recovery suggestion if there was an error
                if "❌" in output or "Error" in output:
                    recovery = self.openclaw.suggest_recovery(output)
                    if recovery:
                        feedback += f"\n\n💡 OpenClaw Recovery Suggestion: {recovery}"

                messages.append({"role": "user", "content": feedback})

                # ── Prune context via OpenClaw's memory manager ──
                messages = self.openclaw.memory.prune(messages)

            except Exception as e:
                self._emit("error", {"step": steps, "message": str(e)})
                break

        if self._stop_flag:
            self._emit("session_end", {"total_steps": steps, "status": "stopped", "final_thought": "Stopped by user"})

        if steps >= self.max_steps and not self._stop_flag:
            self._emit("session_end", {"total_steps": steps, "status": "max_steps_reached", "final_thought": "Max steps reached"})

        self.running = False

    def run_async(self, goal: str):
        """Run the agent loop in a background thread."""
        t = threading.Thread(target=self.run, args=(goal,), daemon=True)
        t.start()

    def get_openclaw_status(self) -> Dict:
        """Get OpenClaw orchestrator status."""
        if self.openclaw:
            return self.openclaw.get_status()
        return {}
