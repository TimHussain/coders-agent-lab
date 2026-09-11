"""Local JSONL tracing through LangChain callbacks, shared by both harnesses."""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


def byte_size(value: Any) -> int:
    return len(json.dumps(value, default=str, ensure_ascii=False).encode("utf-8"))


class LocalTracer(BaseCallbackHandler):
    """Records every model/tool completion, including failures, without a hosted service.

    Tool arguments are recorded for this synthetic lab. Results are measured, not
    copied in full. No model configuration, headers or credentials are written.
    A lock protects parallel tool callbacks. Usage source is explicit.
    """

    def __init__(self, directory: str | Path = "traces"):
        self.run_id = uuid.uuid4().hex
        self.path = Path(directory) / f"{self.run_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._pending: dict[str, dict] = {}

    def event(self, kind: str, **fields) -> None:
        row = {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            **fields,
        }
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")

    def _start(self, run_id, kind: str, **fields):
        with self._lock:
            self._pending[str(run_id)] = {"kind": kind, "started": time.perf_counter(), **fields}

    def _finish(self, run_id, **fields):
        with self._lock:
            item = self._pending.pop(str(run_id), None)
        if item is not None:
            elapsed = (time.perf_counter() - item.pop("started")) * 1000
            self.event(
                item.pop("kind"),
                event_id=str(run_id),
                latency_ms=round(elapsed, 3),
                **item,
                **fields,
            )

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self._start(
            run_id,
            "model",
            input_bytes=byte_size(messages),
            message_count=sum(len(batch) for batch in messages),
        )

    def on_llm_end(self, response, *, run_id, **kwargs):
        message = response.generations[0][0].message
        usage = message.usage_metadata
        self._finish(
            run_id,
            status="ok",
            tool_calls=message.tool_calls,
            result_bytes=byte_size(message.model_dump()),
            input_tokens=usage["input_tokens"] if usage else None,
            output_tokens=usage["output_tokens"] if usage else None,
            total_tokens=usage["total_tokens"] if usage else None,
            token_source=message.response_metadata.get("token_source", "provider")
            if usage
            else "unavailable",
        )

    def on_llm_error(self, error, *, run_id, **kwargs):
        self._finish(
            run_id,
            status="error",
            error_type=type(error).__name__,
            result_bytes=0,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            token_source="unavailable",
        )

    def on_tool_start(self, serialized, input_str, *, run_id, inputs=None, **kwargs):
        self._start(
            run_id,
            "tool",
            name=(serialized or {}).get("name", "unknown"),
            arguments=inputs if inputs is not None else input_str,
        )

    def on_tool_end(self, output, *, run_id, **kwargs):
        status = "error" if getattr(output, "status", None) == "error" else "ok"
        self._finish(run_id, status=status, result_bytes=byte_size(output))

    def on_tool_error(self, error, *, run_id, **kwargs):
        self._finish(run_id, status="error", error_type=type(error).__name__, result_bytes=0)


def summarise_run(path: str | Path) -> dict:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
    model = [r for r in rows if r["kind"] == "model"]
    summary = {
        "turns": len(model),
        "tool_calls": sum(r["kind"] == "tool" for r in rows),
        "total_tokens": sum(r.get("total_tokens") or 0 for r in model),
        "unknown_token_calls": sum(r.get("total_tokens") is None for r in model),
        "estimated_token_calls": sum(r.get("token_source") == "estimated" for r in model),
    }
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise a local agent trace")
    parser.add_argument("path", type=Path)
    summarise_run(parser.parse_args().path)


if __name__ == "__main__":
    main()
