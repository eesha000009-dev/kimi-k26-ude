"""
OpenClaw - The Orchestrator Layer
===================================
The 2nd Pillar of the Kimi K2.6 UDE Architecture.

OpenClaw is an open-source integration framework that intercepts Kimi K2.6's
structured JSON outputs and routes them to the appropriate local system
dependencies. It sits between The Brain (Kimi K2.6 API) and The Sandbox
Execution Layer, providing:

1. Command interception, parsing, and routing
2. Tool registry and dispatch (terminal, MCP, browser, Docker, file ops)
3. Safety validation and permission checking
4. Error recovery, retry logic, and fallback routing
5. Execution telemetry and audit logging
6. Multi-agent coordination for Agent Swarm mode
7. Context memory management (conversation window pruning)

Architecture Flow:
    Brain (Kimi API) → OpenClaw (Orchestrator) → Sandbox (Execution)
                         ↕
                    Tool Registry
                    Safety Layer
                    Error Recovery
                    Audit Logger
"""

import os
import json
import re
import time
import hashlib
import threading
from typing import Optional, List, Dict, Any, Callable
from queue import Queue
from enum import Enum


# ── Routing Types ─────────────────────────────────────────────
class RouteType(Enum):
    """Types of routes OpenClaw can dispatch to."""
    TERMINAL = "terminal"         # Bash command execution
    DOCKER = "docker"             # Docker sandboxed execution
    MCP_TOOL = "mcp_tool"         # Model Context Protocol tool
    FILE_WRITE = "file_write"     # Direct file write operation
    FILE_READ = "file_read"       # Direct file read operation
    BROWSER = "browser"           # Browser automation (Playwright)
    COMPLETE = "complete"         # Task completion signal
    UNKNOWN = "unknown"           # Unrecognized command
    BLOCKED = "blocked"           # Blocked by safety layer


# ── Safety Level ──────────────────────────────────────────────
class SafetyLevel(Enum):
    """Safety levels for command validation."""
    SAFE = "safe"                 # No risk (read-only, file creation)
    CAUTION = "caution"           # Low risk (package install, file modify)
    DANGEROUS = "dangerous"       # High risk (system commands, deletion)
    BLOCKED = "blocked"           # Blocked entirely (rm -rf /, etc.)


# ── Audit Log Entry ──────────────────────────────────────────
class AuditEntry:
    """A single audit log entry for OpenClaw routing decisions."""

    def __init__(self, step: int, route_type: RouteType, command: str,
                 safety: SafetyLevel, result: str, duration_ms: float):
        self.timestamp = time.time()
        self.step = step
        self.route_type = route_type
        self.command = command[:500]
        self.safety = safety
        self.result = result[:500]
        self.duration_ms = duration_ms
        self.checksum = hashlib.md5(command.encode()).hexdigest()[:8]

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "step": self.step,
            "route_type": self.route_type.value,
            "command": self.command,
            "safety": self.safety.value,
            "result": self.result,
            "duration_ms": round(self.duration_ms, 1),
            "checksum": self.checksum,
        }


# ── Command Validator / Safety Layer ─────────────────────────
class SafetyValidator:
    """Validates commands before execution to prevent system damage.

    The safety layer is a core part of OpenClaw. It inspects every
    command that Kimi K2.6 generates before routing it to the
    execution layer, blocking dangerous operations and flagging
    risky ones.
    """

    # Patterns that are always blocked
    BLOCKED_PATTERNS = [
        r"rm\s+-rf\s+/(?!\w)",          # rm -rf / (root delete)
        r"rm\s+-rf\s+~",                 # rm -rf ~ (home delete)
        r"rm\s+-rf\s+\$",                # rm -rf $HOME
        r"dd\s+if=.*of=/dev/",           # dd to device
        r"mkfs\.",                        # Format filesystem
        r":\(\)\{.*;\}",                  # Fork bomb
        r"chmod\s+000\s+/",              # Remove all permissions from root
        r"wget.*\|\s*sh",                # Pipe download to shell
        r"curl.*\|\s*sh",                # Pipe curl to shell
        r">\s*/dev/sd",                   # Write to block device
    ]

    # Patterns that are flagged as dangerous (allowed but logged)
    DANGEROUS_PATTERNS = [
        r"rm\s+-r",                       # Recursive delete
        r"sudo\s+",                        # sudo commands
        r"apt\s+remove",                   # Package removal
        r"pip\s+uninstall",                # pip uninstall
        r"kill\s+-9",                      # Force kill
        r"iptables",                       # Firewall changes
        r"systemctl\s+(stop|disable)",     # Service management
        r"docker\s+rm",                    # Docker container removal
        r"git\s+push\s+--force",          # Force push
        r"DROP\s+TABLE",                   # SQL drop table
        r"TRUNCATE\s+TABLE",              # SQL truncate
    ]

    # Patterns that are caution-level
    CAUTION_PATTERNS = [
        r"pip\s+install",                  # Package install
        r"apt\s+install",                  # System package install
        r"npm\s+install",                  # npm install
        r"git\s+commit",                   # Git commit
        r"git\s+push",                     # Git push
        r"docker\s+run",                   # Docker run
        r"mkdir\s+-p",                     # Recursive mkdir (usually fine)
    ]

    def validate(self, command: str) -> tuple:
        """Validate a command and return (SafetyLevel, reason).

        Returns:
            Tuple of (SafetyLevel, reason_string)
        """
        if not command or not command.strip():
            return SafetyLevel.SAFE, "Empty command"

        cmd_stripped = command.strip()

        # Check blocked patterns first
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, cmd_stripped, re.IGNORECASE):
                return SafetyLevel.BLOCKED, f"Blocked: matches dangerous pattern '{pattern}'"

        # Check dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd_stripped, re.IGNORECASE):
                return SafetyLevel.DANGEROUS, f"Dangerous: matches pattern '{pattern}'"

        # Check caution patterns
        for pattern in self.CAUTION_PATTERNS:
            if re.search(pattern, cmd_stripped, re.IGNORECASE):
                return SafetyLevel.CAUTION, f"Caution: matches pattern '{pattern}'"

        return SafetyLevel.SAFE, "Command appears safe"

    def should_auto_approve(self, safety: SafetyLevel, auto_approve_level: SafetyLevel = SafetyLevel.CAUTION) -> bool:
        """Check if a command at the given safety level should be auto-approved."""
        hierarchy = {
            SafetyLevel.SAFE: 0,
            SafetyLevel.CAUTION: 1,
            SafetyLevel.DANGEROUS: 2,
            SafetyLevel.BLOCKED: 3,
        }
        return hierarchy.get(safety, 3) <= hierarchy.get(auto_approve_level, 1)


# ── Command Router ────────────────────────────────────────────
class CommandRouter:
    """Routes parsed commands to the appropriate execution handler.

    OpenClaw's CommandRouter analyzes the JSON output from Kimi K2.6
    and determines which execution backend should handle it:
    - Terminal commands → CommandExecutor (local or Docker)
    - MCP tool calls → MCPBridge
    - Browser commands → BrowserAutomation
    - File operations → Direct filesystem
    """

    def __init__(self):
        self.handlers = {}
        self.route_stats = {r.value: 0 for r in RouteType}

    def register_handler(self, route_type: RouteType, handler: Callable):
        """Register a handler function for a route type."""
        self.handlers[route_type] = handler

    def route(self, command: str, parsed: Dict) -> tuple:
        """Determine the route type and target handler for a command.

        Args:
            command: The raw command string from Kimi
            parsed: The parsed JSON decision from Kimi

        Returns:
            Tuple of (RouteType, handler_function)
        """
        # Check for completion signal
        if command == "COMPLETE" or not command:
            return RouteType.COMPLETE, self.handlers.get(RouteType.COMPLETE)

        cmd = command.strip()

        # ── MCP Tool Calls ──
        # Detect MCP-style tool calls (prefixed with mcp:// or containing structured tool format)
        if cmd.startswith("mcp://") or "mcp_tool" in parsed:
            return RouteType.MCP_TOOL, self.handlers.get(RouteType.MCP_TOOL)

        # ── Browser Commands ──
        if any(cmd.startswith(prefix) for prefix in ["browser://", "playwright ", "screenshot"]):
            return RouteType.BROWSER, self.handlers.get(RouteType.BROWSER)

        # ── File Write Detection ──
        # Detect cat > file, echo > file, tee, etc.
        file_write_patterns = [
            r"cat\s*<<.*>\s*",           # cat heredoc redirect
            r"echo\s+.*>\s+",            # echo redirect
            r"tee\s+",                    # tee command
            r"printf\s+.*>\s+",          # printf redirect
        ]
        for pattern in file_write_patterns:
            if re.search(pattern, cmd):
                return RouteType.FILE_WRITE, self.handlers.get(RouteType.FILE_WRITE)

        # ── File Read Detection ──
        file_read_cmds = ["cat ", "head ", "tail ", "less ", "more ", "wc ", "file "]
        if any(cmd.startswith(f) for f in file_read_cmds) and ">" not in cmd:
            return RouteType.FILE_READ, self.handlers.get(RouteType.FILE_READ)

        # ── Docker Detection ──
        # If Docker mode is enabled, check for docker-specific commands
        if cmd.startswith("docker "):
            return RouteType.DOCKER, self.handlers.get(RouteType.DOCKER)

        # ── Default: Terminal Execution ──
        return RouteType.TERMINAL, self.handlers.get(RouteType.TERMINAL)

    def record_route(self, route_type: RouteType):
        """Record a routing decision for telemetry."""
        self.route_stats[route_type.value] = self.route_stats.get(route_type.value, 0) + 1

    def get_stats(self) -> Dict:
        """Get routing statistics."""
        total = sum(self.route_stats.values())
        return {
            "total_routes": total,
            "by_type": dict(self.route_stats),
            "percentages": {
                k: round(v / total * 100, 1) if total > 0 else 0
                for k, v in self.route_stats.items()
            } if total > 0 else {},
        }


# ── Context Memory Manager ───────────────────────────────────
class ContextMemoryManager:
    """Manages the conversation context window for Kimi K2.6.

    Kimi K2.6 has a large context window, but long-running agent loops
    with 4000 steps can accumulate massive conversation histories. This
    manager handles:
    - Summarizing old conversation turns
    - Pruning low-value exchanges
    - Maintaining a rolling context window
    """

    def __init__(self, max_messages: int = 100, summarize_threshold: int = 80):
        self.max_messages = max_messages
        self.summarize_threshold = summarize_threshold
        self.summaries = []

    def should_prune(self, messages: List[Dict]) -> bool:
        """Check if the conversation history needs pruning."""
        return len(messages) > self.summarize_threshold

    def prune(self, messages: List[Dict], summarizer: Callable = None) -> List[Dict]:
        """Prune the conversation history, keeping system prompt and recent messages.

        If a summarizer function is provided, old messages are summarized.
        Otherwise, they're simply dropped.
        """
        if len(messages) <= self.max_messages:
            return messages

        # Always keep the system prompt (first message)
        system_msg = messages[0] if messages and messages[0].get("role") == "system" else None

        # Keep the most recent messages
        keep_count = self.max_messages - 1  # -1 for system prompt
        recent = messages[-keep_count:]

        # Summarize older messages if possible
        older = messages[1:-keep_count] if len(messages) > keep_count + 1 else []
        if older and summarizer:
            summary_text = summarizer(older)
            self.summaries.append(summary_text)
            summary_msg = {
                "role": "user",
                "content": f"[Context Summary - {len(older)} previous exchanges]: {summary_text}"
            }
            result = [system_msg, summary_msg] if system_msg else [summary_msg]
            result.extend(recent)
            return result

        # Simple pruning: keep system + recent
        result = [system_msg] if system_msg else []
        result.extend(recent)
        return result

    def get_token_estimate(self, messages: List[Dict]) -> int:
        """Rough token estimate for the conversation."""
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars // 4  # Rough: 4 chars per token


# ── OpenClaw Orchestrator ────────────────────────────────────
class OpenClaw:
    """OpenClaw - The Orchestrator Layer (2nd Pillar of UDE).

    OpenClaw intercepts Kimi K2.6's structured JSON outputs and routes
    them to the appropriate local system dependencies. It provides the
    intelligent middleware layer between the AI Brain and the Execution
    Sandbox.

    Core Responsibilities:
    1. Intercept and parse Kimi's JSON responses
    2. Route commands to the correct execution handler
    3. Validate command safety before execution
    4. Manage execution context and conversation memory
    5. Handle errors and provide recovery strategies
    6. Log all routing decisions for audit and debugging
    7. Coordinate Agent Swarm activities
    """

    def __init__(self, event_queue: Queue = None):
        self.event_queue = event_queue or Queue()
        self.safety = SafetyValidator()
        self.router = CommandRouter()
        self.memory = ContextMemoryManager()
        self.audit_log: List[AuditEntry] = []
        self.step_counter = 0
        self.auto_approve_level = SafetyLevel.CAUTION
        self.pending_approvals: List[Dict] = []
        self._lock = threading.Lock()

        # Execution backends (registered by the main agent)
        self._terminal_executor = None
        self._docker_executor = None
        self._mcp_bridge = None
        self._browser_automation = None
        self._workspace_dir = os.path.expanduser("~/kimi_ude_workspace")

    def register_backends(self, terminal=None, docker=None, mcp=None, browser=None, workspace_dir=None):
        """Register execution backends.

        This is called by KimiUDEAgent during initialization to connect
        OpenClaw to the actual execution layer.
        """
        self._terminal_executor = terminal
        self._docker_executor = docker
        self._mcp_bridge = mcp
        self._browser_automation = browser
        if workspace_dir:
            self._workspace_dir = workspace_dir

        # Register handlers with the router
        self.router.register_handler(RouteType.TERMINAL, self._handle_terminal)
        self.router.register_handler(RouteType.DOCKER, self._handle_docker)
        self.router.register_handler(RouteType.MCP_TOOL, self._handle_mcp)
        self.router.register_handler(RouteType.FILE_WRITE, self._handle_file_write)
        self.router.register_handler(RouteType.FILE_READ, self._handle_file_read)
        self.router.register_handler(RouteType.BROWSER, self._handle_browser)
        self.router.register_handler(RouteType.COMPLETE, self._handle_complete)

    def _emit(self, event_type: str, data: Dict):
        """Emit an event to the UI via the event queue."""
        self.event_queue.put({"type": event_type, "data": data})

    # ── Main Routing Method ──────────────────────────────────
    def intercept_and_route(self, raw_response: str, use_docker: bool = False) -> Dict:
        """Intercept Kimi K2.6's response, parse it, validate, and route to execution.

        This is the main entry point for OpenClaw. It:
        1. Parses the JSON response from Kimi
        2. Validates the command for safety
        3. Routes to the appropriate execution handler
        4. Logs the routing decision
        5. Returns the execution result

        Args:
            raw_response: The raw JSON string from Kimi K2.6
            use_docker: Whether to use Docker sandboxing

        Returns:
            Dict with route info, safety assessment, and execution result
        """
        start_time = time.time()
        self.step_counter += 1
        step = self.step_counter

        # ── Step 1: Parse Kimi's Response ──
        parsed = self._parse_response(raw_response)
        if "error" in parsed:
            self._emit("openclaw_error", {"step": step, "message": parsed["error"]})
            return {"success": False, "error": parsed["error"], "step": step}

        thought = parsed.get("thought", "")
        command = parsed.get("command", "")

        # ── Step 2: Check Completion ──
        if command == "COMPLETE" or not command:
            result = {
                "success": True,
                "route": RouteType.COMPLETE.value,
                "safety": SafetyLevel.SAFE.value,
                "thought": thought,
                "command": command,
                "output": "",
                "step": step,
                "is_complete": True,
            }
            self._log_audit(step, RouteType.COMPLETE, command, SafetyLevel.SAFE, "Task complete", 0)
            return result

        # ── Step 3: Route the Command ──
        route_type, handler = self.router.route(command, parsed)

        # If Docker mode is requested, override terminal with Docker
        if use_docker and route_type == RouteType.TERMINAL:
            route_type = RouteType.DOCKER
            handler = self._handle_docker

        # ── Step 4: Safety Validation ──
        safety_level, safety_reason = self.safety.validate(command)

        if safety_level == SafetyLevel.BLOCKED:
            self._emit("openclaw_blocked", {
                "step": step, "command": command, "reason": safety_reason
            })
            self._log_audit(step, RouteType.BLOCKED, command, safety_level, safety_reason, 0)
            return {
                "success": False,
                "route": RouteType.BLOCKED.value,
                "safety": safety_level.value,
                "thought": thought,
                "command": command,
                "output": f"⛔ Command blocked by OpenClaw safety layer: {safety_reason}",
                "step": step,
                "is_complete": False,
            }

        # ── Step 5: Check Auto-Approval ──
        if not self.safety.should_auto_approve(safety_level, self.auto_approve_level):
            # For dangerous commands, we still execute but log prominently
            self._emit("openclaw_dangerous", {
                "step": step,
                "command": command,
                "safety": safety_level.value,
                "reason": safety_reason,
            })

        # ── Step 6: Execute via Handler ──
        self._emit("openclaw_routing", {
            "step": step,
            "route": route_type.value,
            "safety": safety_level.value,
            "command": command[:200],
        })

        execution_output = ""
        if handler:
            try:
                execution_output = handler(command)
            except Exception as e:
                execution_output = f"❌ Handler error: {str(e)}"
                self._emit("openclaw_handler_error", {
                    "step": step, "route": route_type.value, "error": str(e)
                })
        else:
            execution_output = f"⚠ No handler registered for route type: {route_type.value}"

        duration = (time.time() - start_time) * 1000

        # ── Step 7: Log and Return ──
        self._log_audit(step, route_type, command, safety_level, execution_output[:200], duration)
        self.router.record_route(route_type)

        self._emit("openclaw_executed", {
            "step": step,
            "route": route_type.value,
            "safety": safety_level.value,
            "duration_ms": round(duration, 1),
        })

        return {
            "success": True,
            "route": route_type.value,
            "safety": safety_level.value,
            "thought": thought,
            "command": command,
            "output": execution_output,
            "step": step,
            "is_complete": False,
            "duration_ms": round(duration, 1),
        }

    # ── Response Parser ──────────────────────────────────────
    def _parse_response(self, raw_response: str) -> Dict:
        """Parse Kimi K2.6's JSON response, handling various formats."""
        if not raw_response:
            return {"error": "Empty response from Kimi"}

        # Try direct JSON parse
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code blocks
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw_response)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding JSON object in text
        match = re.search(r'\{[^{}]*"thought"[^{}]*"command"[^{}]*\}', raw_response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return {"error": f"Could not parse response as JSON", "raw": raw_response[:300]}

    # ── Execution Handlers ───────────────────────────────────
    def _handle_terminal(self, command: str) -> str:
        """Handle terminal/bash command execution."""
        if self._terminal_executor:
            return self._terminal_executor.execute(command)
        return "⚠ Terminal executor not registered"

    def _handle_docker(self, command: str) -> str:
        """Handle Docker sandboxed command execution."""
        if self._docker_executor:
            return self._docker_executor.execute(command)
        # Fallback: use terminal with docker prefix
        if self._terminal_executor:
            return self._terminal_executor.execute(command)
        return "⚠ Docker executor not registered"

    def _handle_mcp(self, command: str) -> str:
        """Handle MCP tool calls."""
        if self._mcp_bridge:
            # Parse MCP command format: mcp://tool_name/param1/param2
            if command.startswith("mcp://"):
                parts = command[6:].split("/")
                tool_name = parts[0]
                params = {"path": parts[1] if len(parts) > 1 else ""}
                return str(self._mcp_bridge.execute_tool(tool_name, params))
            return str(self._mcp_bridge.execute_tool("run_command", {"command": command}))
        return "⚠ MCP bridge not registered"

    def _handle_file_write(self, command: str) -> str:
        """Handle file write operations with workspace safety."""
        if self._terminal_executor:
            return self._terminal_executor.execute(command)
        return "⚠ Terminal executor not registered for file write"

    def _handle_file_read(self, command: str) -> str:
        """Handle file read operations."""
        if self._terminal_executor:
            return self._terminal_executor.execute(command)
        return "⚠ Terminal executor not registered for file read"

    def _handle_browser(self, command: str) -> str:
        """Handle browser automation commands."""
        if self._browser_automation:
            return self._browser_automation(command)
        # Try MCP bridge browser tools
        if self._mcp_bridge:
            if "screenshot" in command.lower():
                return str(self._mcp_bridge.execute_tool("browser_screenshot", {}))
            elif "open" in command.lower() or "://" in command:
                url = re.search(r'https?://\S+', command)
                if url:
                    return str(self._mcp_bridge.execute_tool("browser_open", {"url": url.group(0)}))
        return "⚠ Browser automation not available (install playwright: pip install playwright && playwright install)"

    def _handle_complete(self, command: str) -> str:
        """Handle task completion signal."""
        return ""

    # ── Audit Logging ────────────────────────────────────────
    def _log_audit(self, step: int, route_type: RouteType, command: str,
                   safety: SafetyLevel, result: str, duration_ms: float):
        """Add an entry to the audit log."""
        with self._lock:
            entry = AuditEntry(step, route_type, command, safety, result, duration_ms)
            self.audit_log.append(entry)

    def get_audit_log(self, last_n: int = 50) -> List[Dict]:
        """Get the last N audit log entries."""
        with self._lock:
            return [e.to_dict() for e in self.audit_log[-last_n:]]

    # ── Status and Telemetry ─────────────────────────────────
    def get_status(self) -> Dict:
        """Get OpenClaw orchestrator status and telemetry."""
        return {
            "steps_processed": self.step_counter,
            "routing_stats": self.router.get_stats(),
            "audit_entries": len(self.audit_log),
            "auto_approve_level": self.auto_approve_level.value,
            "pending_approvals": len(self.pending_approvals),
            "memory_messages": 0,  # Updated externally
            "backends": {
                "terminal": self._terminal_executor is not None,
                "docker": self._docker_executor is not None,
                "mcp": self._mcp_bridge is not None,
                "browser": self._browser_automation is not None,
            },
        }

    # ── Error Recovery ───────────────────────────────────────
    def suggest_recovery(self, error_output: str) -> Optional[str]:
        """Analyze an error output and suggest a recovery strategy.

        This is a simple rule-based recovery system. For more advanced
        recovery, the error output is fed back to Kimi K2.6 in the
        agent loop, which can self-correct.
        """
        error_lower = error_output.lower()

        # Command not found → suggest installation
        if "command not found" in error_lower or "not recognized" in error_lower:
            cmd = error_lower.split("command not found")[0].strip().split()[-1] if "command not found" in error_lower else ""
            return f"Try installing the missing command: apt install {cmd} or pip install {cmd}"

        # Permission denied → suggest sudo or fix permissions
        if "permission denied" in error_lower:
            return "Permission denied. Try with sudo or check file permissions."

        # Module not found → suggest pip install
        if "modulenotfounderror" in error_lower or "no module named" in error_lower:
            module = re.search(r"No module named ['\"]?(\w+)", error_output)
            if module:
                return f"Missing module: pip install {module.group(1)}"

        # Syntax error → generic advice
        if "syntaxerror" in error_lower or "syntax error" in error_lower:
            return "Syntax error detected. Review the code for typos or incorrect formatting."

        # Network error → suggest retry
        if "connection" in error_lower or "timeout" in error_lower:
            return "Network error. Check your connection and retry."

        # Port in use → suggest killing process
        if "address already in use" in error_lower or "port" in error_lower:
            return "Port already in use. Kill the existing process or use a different port."

        return None  # No specific recovery suggestion
