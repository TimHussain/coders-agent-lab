"""Harness contracts are independent of provider intelligence or a paid API key."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.errors import GraphRecursionError

from agentlab.harness.lc_agent import build_agent, build_middleware
from agentlab.harness.models import StubChatModel, estimate_tokens, get_model
from agentlab.harness.raw_loop import LoopConfig, compact_messages, dispatch_tool, run_agent
from agentlab.harness.trace import LocalTracer, summarise_run


def echo(value: str = "ok") -> str:
    """Return a test observation unchanged."""
    return value


ECHO = StructuredTool.from_function(echo)


def scripted(name="echo", args=None, count=1, repeat=False):
    return StubChatModel(
        steps=[[{"name": name, "args": args or {"value": "observed-42"}}] for _ in range(count)],
        repeat=repeat,
    )


@pytest.mark.smoke
def test_stub_model_really_calls_tools():
    model = scripted().bind_tools([ECHO])
    first = model.invoke([HumanMessage(content="Report")])
    assert first.tool_calls[0]["name"] == "echo"
    assert first.tool_calls[0]["args"] == {"value": "observed-42"}
    final = model.invoke(
        [
            HumanMessage(content="Report"),
            first,
            ToolMessage(content="observed-42", tool_call_id=first.tool_calls[0]["id"]),
        ]
    )
    assert not final.tool_calls and "observed-42" in final.content
    assert first.usage_metadata["total_tokens"] > 0


@pytest.mark.smoke
def test_provider_default_and_missing_key(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    assert isinstance(get_model(), StubChatModel)
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        get_model()
    monkeypatch.setenv("MODEL_PROVIDER", "unknown")
    with pytest.raises(ValueError, match="stub or anthropic"):
        get_model()


@pytest.mark.smoke
def test_local_trace_records_usage_and_tools(tmp_path):
    trace = LocalTracer(tmp_path)
    bound = scripted().bind_tools([ECHO])
    messages = [HumanMessage(content="Report")]
    first = bound.invoke(messages, config={"callbacks": [trace]})
    observation = ECHO.invoke(first.tool_calls[0], config={"callbacks": [trace]})
    bound.invoke([*messages, first, observation], config={"callbacks": [trace]})
    rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert [r["kind"] for r in rows] == ["model", "tool", "model"]
    assert rows[1]["arguments"] == {"value": "observed-42"}
    assert all(r["latency_ms"] >= 0 and r["result_bytes"] > 0 for r in rows)
    summary = summarise_run(trace.path)
    assert summary["turns"] == 2 and summary["tool_calls"] == 1
    assert summary["total_tokens"] == sum(r.get("total_tokens", 0) for r in rows)
    assert summary["estimated_token_calls"] == 2


def test_loop_terminal_condition():
    result = run_agent(scripted(), [ECHO], "Report")
    assert result.stop_reason == "final"
    assert result.turns == 2 and result.tool_calls == 1
    assert "observed-42" in result.answer


@pytest.mark.parametrize("max_turns", [1, 2, 4])
def test_loop_max_turns(max_turns):
    result = run_agent(
        scripted(repeat=True),
        [ECHO],
        "Keep going",
        LoopConfig(max_turns=max_turns, max_tool_calls=100),
    )
    assert result.turns == max_turns, "Stop before the next model call, not afterwards."
    assert result.stop_reason == "max_turns"
    assert "turn" in result.answer.lower()


@pytest.mark.parametrize("budget", [0, 1, 3])
def test_loop_tool_budget_cannot_overshoot_parallel_batch(budget):
    calls = []

    def counted(value: str) -> str:
        """Record actual execution."""
        calls.append(value)
        return value

    tool = StructuredTool.from_function(counted)
    model = StubChatModel(
        steps=[[{"name": "counted", "args": {"value": str(i)}} for i in range(6)]], repeat=True
    )
    result = run_agent(model, [tool], "Run a batch", LoopConfig(max_tool_calls=budget))
    assert len(calls) == result.tool_calls == budget, "Check budget before EVERY tool invocation."
    assert result.stop_reason == "max_tool_calls" and "tool" in result.answer.lower()
    ai_ids = {c["id"] for m in result.messages if isinstance(m, AIMessage) for c in m.tool_calls}
    observed_ids = {m.tool_call_id for m in result.messages if isinstance(m, ToolMessage)}
    assert ai_ids <= observed_ids, "Even skipped pending calls need matching ToolMessages."


def test_loop_recovers_from_tool_exception():
    def flaky() -> str:
        """An unavailable test tool."""
        raise RuntimeError("private-token-do-not-copy")

    model = StubChatModel(
        steps=[[{"name": "flaky", "args": {}}], [{"name": "echo", "args": {"value": "recovered"}}]]
    )
    result = run_agent(model, [StructuredTool.from_function(flaky), ECHO], "Recover")
    observations = [m for m in result.messages if isinstance(m, ToolMessage)]
    assert observations[0].status == "error"
    assert "RuntimeError" in observations[0].content
    assert any(word in observations[0].content.lower() for word in ("retry", "correct", "choose"))
    assert "private-token" not in observations[0].content
    assert result.stop_reason == "final" and "recovered" in result.answer


def test_dispatch_unknown_and_invalid_args():
    unknown = dispatch_tool({"id": "u", "name": "missing", "args": {}}, {"echo": ECHO}, frozenset())
    assert unknown.status == "error" and unknown.tool_call_id == "u"
    invalid = dispatch_tool(
        {"id": "v", "name": "echo", "args": {"value": {}}}, {"echo": ECHO}, frozenset()
    )
    assert invalid.status == "error" and invalid.tool_call_id == "v"


def test_guardrail_prevents_execution():
    executed = []

    def denied() -> str:
        """A tool whose execution is forbidden by this harness."""
        executed.append(True)
        return "should not happen"

    model = StubChatModel(steps=[[{"name": "denied", "args": {}}]])
    result = run_agent(
        model,
        [StructuredTool.from_function(denied)],
        "Call denied",
        LoopConfig(denied_tools=frozenset({"denied"})),
    )
    assert not executed, "A guardrail must run before dispatch."
    errors = [m for m in result.messages if isinstance(m, ToolMessage)]
    assert errors[0].status == "error" and "denied" in errors[0].content.lower()


def test_compaction_preserves_tail_and_reduces_tokens():
    messages = [SystemMessage(content="Only use allowed reporting tools.")]
    for i in range(12):
        messages.extend(
            [
                HumanMessage(content=f"Question {i} " + "detail " * 200),
                AIMessage(content=f"Observation {i} " + "data " * 200),
            ]
        )
    original = [m.model_dump() for m in messages]
    compacted = compact_messages(messages, token_threshold=500, keep_last=4)
    assert len(compacted) < len(messages), "H2.3: Replace older turns with a compact summary."
    assert [m.model_dump() for m in compacted[-4:]] == original[-4:]
    assert compacted[0] == messages[0]
    assert estimate_tokens(compacted) < estimate_tokens(messages)
    assert [m.model_dump() for m in messages] == original, "Don't mutate input history."
    assert sum(isinstance(m, SystemMessage) for m in compacted) == 1
    assert any("summary" in str(m.content).lower() for m in compacted[1:-4])


def test_compaction_preserves_tool_call_pairs():
    messages = [
        HumanMessage(content="old " * 3000),
        AIMessage(content="old response " * 3000),
        AIMessage(content="", tool_calls=[{"name": "echo", "args": {}, "id": "pair"}]),
        ToolMessage(content="observation", tool_call_id="pair"),
        HumanMessage(content="Recent question"),
    ]
    compacted = compact_messages(messages, token_threshold=100, keep_last=2)
    ids = {c["id"] for m in compacted if isinstance(m, AIMessage) for c in m.tool_calls}
    assert all(m.tool_call_id in ids for m in compacted if isinstance(m, ToolMessage))
    assert compacted[-2:] == messages[-2:]
    assert estimate_tokens(compacted) < estimate_tokens(messages)


def test_compaction_below_threshold():
    messages = [HumanMessage(content="Small question")]
    assert compact_messages(messages, token_threshold=1000, keep_last=4) == messages


def test_loop_actually_invokes_compaction(tmp_path):
    trace = LocalTracer(tmp_path)
    model = scripted(args={"value": "large result " * 500}, count=6)
    result = run_agent(model, [ECHO], "Report", LoopConfig(token_threshold=500, keep_last=2), trace)
    assert result.compactions > 0, "The loop must use compaction, not just define the helper."
    events = [json.loads(line) for line in trace.path.read_text().splitlines()]
    compacted = [e for e in events if e["kind"] == "compaction"]
    assert compacted and all(e["after_tokens"] < e["before_tokens"] for e in compacted)


def install_anthropic_mock(monkeypatch):
    """Mock only the HTTP boundary; real ChatAnthropic serialises/decodes tool messages.

    This proves adapter compatibility, not live API availability or model quality.
    """
    from anthropic.types import Message
    from langchain_anthropic import ChatAnthropic

    payloads = []

    def create(self, payload):
        payloads.append(payload)
        if len(payloads) == 1:
            content = [
                {
                    "type": "tool_use",
                    "id": "anthropic_call_1",
                    "name": "echo",
                    "input": {"value": "observed-42"},
                }
            ]
            stop = "tool_use"
        else:
            assert "tool_result" in json.dumps(payload["messages"])
            content = [{"type": "text", "text": "Observed: observed-42"}]
            stop = "end_turn"
        response = Message.model_validate(
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-6",
                "content": content,
                "stop_reason": stop,
                "stop_sequence": None,
                "usage": {"input_tokens": 20, "output_tokens": 10},
            }
        )
        return SimpleNamespace(parse=lambda: response)

    async def acreate(self, payload):
        return create(self, payload)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setattr(ChatAnthropic, "_create", create)
    monkeypatch.setattr(ChatAnthropic, "_acreate", acreate)
    return payloads


@pytest.mark.parametrize("provider", ["stub", "anthropic"])
def test_same_raw_agent_with_both_providers(provider, monkeypatch):
    payloads = install_anthropic_mock(monkeypatch) if provider == "anthropic" else []
    monkeypatch.setenv("MODEL_PROVIDER", provider)
    model = get_model(steps=[[{"name": "echo", "args": {"value": "observed-42"}}]])
    result = run_agent(model, [ECHO], "Call echo with observed-42, then report the observation.")
    assert result.stop_reason == "final" and result.turns == 2 and result.tool_calls == 1
    assert "observed-42" in result.answer
    if provider == "anthropic":
        assert len(payloads) == 2 and payloads[0]["tools"][0]["name"] == "echo"


async def invoke_lc(model, tools, **controls):
    agent = create_agent(model, tools, middleware=build_middleware(**controls))
    try:
        return await agent.ainvoke(
            {"messages": [("user", "Run the scenario")]}, config={"recursion_limit": 30}
        )
    except GraphRecursionError:
        pytest.fail(
            "H2.B: Add model/tool call limits with clean termination; graph recursion is a "
            "safety backstop, not your stopping rule.",
            pytrace=False,
        )


async def test_lc_tool_budget():
    result = await invoke_lc(scripted(repeat=True), [ECHO], max_tool_calls=2)
    observations = [
        m for m in result["messages"] if isinstance(m, ToolMessage) and m.status != "error"
    ]
    assert len(observations) <= 2, "H2.B: ToolCallLimitMiddleware must stop excess calls."
    assert "limit" in str(result["messages"][-1].content).lower()


async def test_lc_model_budget():
    result = await invoke_lc(scripted(repeat=True), [ECHO], max_turns=2, max_tool_calls=100)
    calls = [m for m in result["messages"] if isinstance(m, AIMessage) and m.tool_calls]
    assert len(calls) <= 2
    assert "limit" in str(result["messages"][-1].content).lower()


async def test_lc_denied_tool():
    executed = []

    def denied() -> str:
        """Must not execute."""
        executed.append(True)
        return "executed"

    result = await invoke_lc(
        StubChatModel(steps=[[{"name": "denied", "args": {}}]]),
        [StructuredTool.from_function(denied)],
        denied_tools=frozenset({"denied"}),
    )
    assert not executed, "H2.B: Add the guardrail before tool dispatch."
    assert "denied" in str(result["messages"][-1].content).lower()


async def test_lc_recovers_from_tool_error():
    def broken() -> str:
        """Simulated outage."""
        raise RuntimeError("private-detail")

    model = StubChatModel(
        steps=[[{"name": "broken", "args": {}}], [{"name": "echo", "args": {"value": "recovered"}}]]
    )
    try:
        result = await invoke_lc(model, [StructuredTool.from_function(broken), ECHO])
    except RuntimeError:
        pytest.fail(
            "H2.B: Add async tool-error middleware that returns an actionable ToolMessage.",
            pytrace=False,
        )
    observations = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert observations[0].status == "error" and "choose" in observations[0].content.lower()
    assert "private-detail" not in observations[0].content
    assert "recovered" in str(result["messages"][-1].content)


async def test_lc_summarisation_runs():
    model = StubChatModel(steps=[])
    agent = create_agent(
        model, [ECHO], middleware=build_middleware(token_threshold=400, keep_last=2)
    )
    history = [
        HumanMessage(content="question " * 1000),
        AIMessage(content="observation " * 1000),
        HumanMessage(content="Recent question"),
        AIMessage(content="Recent answer"),
    ]
    result = await agent.ainvoke({"messages": history})
    assert estimate_tokens(result["messages"]) < estimate_tokens(history), (
        "H2.B: Add summarisation middleware and lower its threshold for this test."
    )
    assert any("Earlier context" in str(m.content) for m in result["messages"])


@pytest.mark.smoke
async def test_lc_uses_real_http_mcp_server(mcp_url, tmp_path):
    trace = LocalTracer(tmp_path)
    agent = await build_agent(StubChatModel(), mcp_url)
    result = await agent.ainvoke(
        {"messages": [("user", "Report August totals")]}, config={"callbacks": [trace]}
    )
    observations = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert observations and "impressions" in str(observations[0].content)
    summary = summarise_run(trace.path)
    assert summary["turns"] == 2 and summary["tool_calls"] == 1


@pytest.mark.parametrize("provider", ["stub", "anthropic"])
async def test_same_lc_agent_with_both_providers(provider, monkeypatch):
    if provider == "anthropic":
        install_anthropic_mock(monkeypatch)
    monkeypatch.setenv("MODEL_PROVIDER", provider)
    model = get_model(steps=[[{"name": "echo", "args": {"value": "observed-42"}}]])
    result = await invoke_lc(model, [ECHO])
    assert "observed-42" in str(result["messages"][-1].content)


@pytest.mark.live
def test_live_anthropic_only_with_explicit_opt_in(monkeypatch):
    import os

    if os.getenv("AGENTLAB_LIVE_TEST") != "1":
        pytest.skip(
            "Optional live Anthropic test: set AGENTLAB_LIVE_TEST=1 and provide a key in .env."
        )
    from dotenv import dotenv_values

    key = dotenv_values(".env").get("ANTHROPIC_API_KEY")
    if not key:
        pytest.fail(
            "Live opt-in needs ANTHROPIC_API_KEY in ignored .env; offline tests need no key."
        )
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    result = run_agent(
        get_model(), [ECHO], "You must call echo with value observed-42, then report it."
    )
    assert (
        result.stop_reason == "final" and result.tool_calls >= 1 and "observed-42" in result.answer
    )
