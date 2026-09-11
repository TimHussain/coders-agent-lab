"""Run with python -m agentlab.mcp_server.server; endpoint /mcp on loopback only."""

import os

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from agentlab.mcp_server import tools

mcp = FastMCP(
    "Agent Lab",
    host="127.0.0.1",
    port=int(os.getenv("AGENTLAB_MCP_PORT", "8765")),
    stateless_http=True,
    json_response=True,
    instructions="Synthetic reporting warehouse. Prefer aggregate tools; use server-computed deltas.",
)
for fn in (
    tools.totals_for_period,
    tools.publisher_mix,
    tools.period_over_period,
    tools.pacing_against_plan,
    tools.run_query,
    tools.refusals,
):
    # No description override: this docstring becomes the model's tool-selection interface.
    mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(fn)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
