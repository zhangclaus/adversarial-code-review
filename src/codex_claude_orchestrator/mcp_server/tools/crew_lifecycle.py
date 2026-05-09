from __future__ import annotations

import json

from mcp.server import Server
from mcp.types import TextContent


def register_lifecycle_tools(server: Server, controller) -> None:

    @server.tool("crew_verify")
    async def crew_verify(
        crew_id: str,
        command: str,
        worker_id: str | None = None,
    ) -> list[TextContent]:
        """Run a verification command (e.g. pytest, ruff check)."""
        try:
            result = controller.verify(crew_id=crew_id, command=command, worker_id=worker_id)
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
        except FileNotFoundError as exc:
            return [TextContent(type="text", text=json.dumps({"error": str(exc)}, ensure_ascii=False))]
        except ValueError as exc:
            return [TextContent(type="text", text=json.dumps({"error": str(exc)}, ensure_ascii=False))]
        except Exception as exc:
            return [TextContent(type="text", text=json.dumps({"error": f"internal: {exc}"}, ensure_ascii=False))]
