"""Hour two A: the loop structure is visible; the exercise logic is yours."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from agentlab.harness.models import get_model
from agentlab.harness.trace import LocalTracer, summarise_run
from agentlab.mcp_server import tools as reporting


@dataclass(frozen=True)
class LoopConfig:
    max_turns: int = 8
    max_tool_calls: int = 10
    token_threshold: int = 3000
    keep_last: int = 4
    denied_tools: frozenset[str] = field(default_factory=lambda: frozenset({"run_query"}))

    def __post_init__(self):
        if self.max_turns < 1 or self.max_tool_calls < 0:
            raise ValueError("max_turns must be positive; max_tool_calls must be non-negative")
        if self.token_threshold < 1 or self.keep_last < 1:
            raise ValueError("token_threshold and keep_last must be positive")


@dataclass
class RunResult:
    messages: list[BaseMessage]
    turns: int
    tool_calls: int
    stop_reason: str
    answer: str
    compactions: int = 0


def compact_messages(
    messages: list[BaseMessage], token_threshold: int, keep_last: int
) -> list[BaseMessage]:
    """Above the estimated token threshold, replace old turns with a short summary.

    Keep leading SystemMessages and the last N messages byte-for-byte. Expand
    that tail backwards when needed to keep AI tool calls with their ToolMessages.
    Summary must be a labelled, lossy HumanMessage, never a new system instruction.
    Reduce estimated tokens when removable history exists; otherwise return the
    original history. Do not mutate caller-owned messages. See test_compaction_*.
    """
    raise NotImplementedError(
        "H2.3: Implement compact_messages: summarise old turns, preserve tail."
    )


def dispatch_tool(
    call: dict,
    tools: dict[str, BaseTool],
    denied_tools: frozenset[str],
    tracer: LocalTracer | None = None,
) -> ToolMessage:
    """Return a ToolMessage with the original call id for success, denial or failure.

    Check the deny list BEFORE execution. Count attempted calls in the loop even
    on denial/error. Unknown tool, invalid arguments or exceptions become concise,
    actionable errors: name the failure type and suggest correcting arguments or
    choosing a supported tool. Never leak exception details/credentials. Continue
    the loop after errors. Pass tracer as a callback to BaseTool.invoke.
    """
    raise NotImplementedError(
        "H2.2: Implement dispatch_tool: safe errors, matching call ids, guardrail."
    )


def run_agent(
    model: BaseChatModel,
    tools: list[BaseTool],
    prompt: str,
    config: LoopConfig | None = None,
    tracer: LocalTracer | None = None,
) -> RunResult:
    """Call -> dispatch tools -> observe -> call, using only BaseChatModel interfaces.

    Bind supplied tools once. On every turn: compact, call with local callbacks,
    append AIMessage, finish if no tool calls, otherwise dispatch each call and
    append matching ToolMessages. Enforce max_turns and max_tool_calls BEFORE the
    next model/tool call, including parallel batches; never overshoot or hang.
    On a limit, resolve remaining call ids with skipped ToolMessages and finish
    with stop_reason=max_turns or max_tool_calls and a human-readable explanation.
    A normal terminal response gives stop_reason=final. Trace compactions and stop.
    Nothing in this loop may branch on MODEL_PROVIDER. See test_loop_*.
    """
    # 1. Initialise history, bind tools and set counters.
    # 2. Repeat while the model-call budget permits: compact -> call -> observe.
    # 3. Dispatch within the remaining tool budget, then loop or return RunResult.
    raise NotImplementedError(
        "H2.1: Implement run_agent: call, tool, observe, stop within both budgets."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the hand-written workshop harness")
    parser.add_argument("prompt", nargs="?", default="Report August 2026 delivery totals.")
    tracer = LocalTracer()
    functions = [
        reporting.totals_for_period,
        reporting.publisher_mix,
        reporting.period_over_period,
        reporting.pacing_against_plan,
        reporting.run_query,
        reporting.refusals,
    ]
    result = run_agent(
        get_model(),
        [StructuredTool.from_function(fn) for fn in functions],
        parser.parse_args().prompt,
        tracer=tracer,
    )
    print(result.answer)
    print(f"Stopped: {result.stop_reason}; trace: {tracer.path}")
    summarise_run(tracer.path)


if __name__ == "__main__":
    main()
