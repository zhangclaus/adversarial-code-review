from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from codex_claude_orchestrator.mcp_server.tools.crew_lifecycle import register_lifecycle_tools
from codex_claude_orchestrator.mcp_server.tools.crew_context import register_context_tools
from codex_claude_orchestrator.mcp_server.tools.crew_decision import register_decision_tools


def create_server(controller=None) -> FastMCP:
    server = FastMCP("crew-orchestrator")

    if controller is not None:
        register_lifecycle_tools(server, controller)
        register_context_tools(server, controller)
        register_decision_tools(server, controller)

    return server
