"""Shared setup. A missing warehouse is a setup error, never an exercise success."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import httpx
import psycopg
import pytest


@pytest.fixture(autouse=True)
def local_provider(monkeypatch):
    # Tests are reproducible even when the developer has a provider/key in their shell.
    monkeypatch.setenv("MODEL_PROVIDER", "stub")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture(scope="session")
def warehouse():
    from agentlab.db import fetch_all

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(
                host="127.0.0.1",
                port=int(os.getenv("AGENTLAB_DB_PORT", "55432")),
                dbname="agentlab",
                user="agentlab_readonly",
                password="agentlab",
                connect_timeout=2,
                autocommit=True,
            ) as conn:
                if conn.execute("SELECT ready FROM seed_status WHERE id=1").fetchone() == (True,):
                    return fetch_all
        except psycopg.Error:
            pass
        time.sleep(1)
    pytest.fail(
        "SETUP: PostgreSQL is not seeded on port 55432. Start Docker, run "
        "`docker compose up -d`, then inspect `docker compose logs db`.",
        pytrace=False,
    )


@pytest.fixture(scope="session")
def mcp_url(warehouse, tmp_path_factory):
    # A real HTTP server tests transport, discovery, schemas and tool invocation.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/mcp"
    env = {**os.environ, "AGENTLAB_MCP_PORT": str(port)}
    path = tmp_path_factory.mktemp("mcp") / "server.log"
    with path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "agentlab.mcp_server.server"], env=env, stdout=log, stderr=log
        )
        try:
            with httpx.Client(trust_env=False) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        pytest.fail(f"SETUP: MCP server exited. See {path}", pytrace=False)
                    try:
                        if client.get(url, timeout=0.3).status_code in (200, 400, 405, 406):
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    pytest.fail(f"SETUP: MCP server did not start. See {path}", pytrace=False)
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
