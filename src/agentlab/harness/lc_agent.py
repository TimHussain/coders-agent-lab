"""Hour two B: same model interface, tools from YOUR HTTP MCP server."""

from __future__ import annotations

import argparse
import asyncio
import os

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_mcp_adapters.client import MultiServerMCPClient

from agentlab.harness.models import get_model
from agentlab.harness.trace import LocalTracer, summarise_run


def build_middleware(
    *,
    max_turns: int = 8,
    max_tool_calls: int = 10,
    token_threshold: int = 3000,
    keep_last: int = 4,
    denied_tools: frozenset[str] = frozenset({"run_query"}),
) -> list:
    """Add controls progressively; tests exercise behaviour, not a checklist of class names.

    Bound model calls and tool calls; summarise older history; convert tool errors
    to actionable observations; refuse denied tools before execution. Implement
    async tool middleware because MCP tools run asynchronously. See test_lc_*.
    """
    middleware = [
        # SummarizationMiddleware: local StubChatModel(scenario="summary") is sufficient.
        # ModelCallLimitMiddleware: max_turns, exit_behavior="end".
        # ToolCallLimitMiddleware: max_tool_calls, exit_behavior="end".
        # Async tool-error recovery and denied-tool guardrail.
    ]
    return middleware


async def build_agent(model: BaseChatModel | None = None, url: str | None = None, **controls):
    client = MultiServerMCPClient(
        {
            "warehouse": {
                "transport": "streamable_http",
                "url": url or os.getenv("AGENTLAB_MCP_URL", "http://127.0.0.1:8765/mcp"),
            }
        },
        handle_tool_errors=False,
    )
    tools = await client.get_tools()
    return create_agent(
        model or get_model(),
        tools,
        system_prompt="Use reporting tools. Report their results without inventing data.",
        middleware=build_middleware(**controls),
    )


async def run(prompt: str) -> None:
    tracer = LocalTracer()
    agent = await build_agent()
    result = await agent.ainvoke(
        {"messages": [("user", prompt)]}, config={"callbacks": [tracer], "recursion_limit": 50}
    )
    print(result["messages"][-1].content)
    print(f"Trace: {tracer.path}")
    summarise_run(tracer.path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LangChain harness over local MCP")
    parser.add_argument("prompt", nargs="?", default="Report August 2026 delivery totals.")
    asyncio.run(run(parser.parse_args().prompt))


if __name__ == "__main__":
    main()
