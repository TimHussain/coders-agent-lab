"""Credential-free, deterministic tool calls behind the real BaseChatModel interface."""

from __future__ import annotations

import json
import math
import os
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field, PrivateAttr

DEFAULT_TOOL_ARGS = {"start_date": "2026-08-01", "end_date": "2026-08-31"}


def estimate_tokens(messages: list[BaseMessage]) -> int:
    """Deterministic UTF-8 estimate; no tokeniser download. Not provider billing tokens."""
    return sum(
        4
        + math.ceil(
            len(
                json.dumps(
                    {"content": m.content, "tool_calls": getattr(m, "tool_calls", [])}, default=str
                ).encode()
            )
            / 4
        )
        for m in messages
    )


class StubChatModel(BaseChatModel):
    """Scripted real tool-calling model for testing, with sequential or parallel calls.

    Each steps entry is a batch of {name,args} calls. Once exhausted, the model
    reports the observed ToolMessage. repeat=True repeats the last batch forever
    to exercise stopping rules. A new instance starts a new run. scenario='summary'
    emits a short extract for LangChain's summarisation middleware.
    """

    steps: list[list[dict[str, Any]]] = Field(
        default_factory=lambda: [[{"name": "totals_for_period", "args": dict(DEFAULT_TOOL_ARGS)}]]
    )
    repeat: bool = False
    scenario: str = "report"
    _turn: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "agentlab-scripted-tool-model"

    @property
    def _identifying_params(self) -> dict:
        return {"scenario": self.scenario, "repeat": self.repeat}

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        # This is the extension BaseChatModel deliberately leaves unimplemented.
        return self.bind(tools=[convert_to_openai_tool(t) for t in tools], **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        turn = self._turn
        self._turn += 1
        if self.scenario == "summary":
            text = str(messages[-1].content)
            message = AIMessage(content="Earlier context (lossy extract): " + text[-500:])
        elif turn < len(self.steps) or (self.repeat and self.steps):
            batch = self.steps[min(turn, len(self.steps) - 1)]
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": f"call_{turn}_{i}",
                        "name": call["name"],
                        "args": call["args"],
                        "type": "tool_call",
                    }
                    for i, call in enumerate(batch)
                ],
            )
        else:
            observations = [m for m in messages if isinstance(m, ToolMessage)]
            observed = str(observations[-1].content)[:1000] if observations else "No tool result."
            message = AIMessage(content="Script complete. Observed: " + observed)
        input_tokens, output_tokens = estimate_tokens(messages), estimate_tokens([message])
        message.usage_metadata = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
        message.response_metadata = {"token_source": "estimated", "model_provider": "stub"}
        return ChatResult(generations=[ChatGeneration(message=message)])


def get_model(**stub_options) -> BaseChatModel:
    """MODEL_PROVIDER=stub by default; anthropic is an explicit optional network path."""
    provider = os.getenv("MODEL_PROVIDER", "stub").strip().lower()
    if provider == "stub":
        return StubChatModel(**stub_options)
    if provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY", "").strip():
            raise ValueError(
                "MODEL_PROVIDER=anthropic needs ANTHROPIC_API_KEY. Use stub without a key."
            )
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            temperature=0,
            max_tokens=1024,
            timeout=30,
            max_retries=0,
        )
    raise ValueError("MODEL_PROVIDER must be stub or anthropic")
