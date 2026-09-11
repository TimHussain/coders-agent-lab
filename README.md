# Coders Agent Lab

Build an MCP reporting server and two agent harnesses in a two-hour workshop.
The data is entirely synthetic. Everything runs locally with the default model;
no service account, API key or hosted database is required.

**A fresh clone is supposed to have failing tests.** The example tool, stub model
and infrastructure checks pass. The exercise tests fail until you implement the
contracts. Start with `pytest -q -m smoke`: that is the setup gate.

Local JSONL files in `./traces/` replace hosted tracing entirely.

## Prerequisites

- Python 3.11 or newer, Git, and Docker Desktop or OrbStack running Linux containers.
- An activated Python virtual environment. On macOS: `python3 -m venv .venv`, then
  `source .venv/bin/activate`. On Windows PowerShell: `py -3 -m venv .venv`, then
  `.venv\Scripts\Activate.ps1`. Create the environment inside the cloned folder,
  or activate an existing workshop environment before setup.
- Ports 55432 (Postgres) and 8765 (MCP) available. Allow roughly 1 GB of Docker disk
  space. Downloads need internet access; the default running lab does not.
- Your existing Claude Code installation for the registration exercise. The Python
  lab works without Claude Code. Claude Code itself still needs its usual access;
  the stub model does not replace Claude Code's own model.

## Four setup commands

Paste the kick-off prompt into Claude Code and let it work through this section for you.

Use the repository URL supplied by your facilitator. If you received a ZIP,
extract it and open a terminal in `coders-agent-lab` instead of cloning.

```sh
git clone https://github.com/TimHussain/coders-agent-lab.git coders-agent-lab && cd coders-agent-lab
docker compose up -d
pip install -e ".[dev]"
pytest -q
```

PowerShell 5 users: run `git clone` and `cd coders-agent-lab` as separate commands;
PowerShell 7 supports `&&`. Use `python -m pip` / `python -m pytest` if your shell's
`pip` or `pytest` belongs to a different Python environment.

### Kick-off prompt

Paste this into Claude Code. You direct and review the work; the agent runs the commands.

> Set up https://github.com/TimHussain/coders-agent-lab locally, following its README.
> Create and use a Python virtual environment, start the database, install the pinned
> development dependencies, and run the full tests and the smoke checks. Do not read
> FACILITATOR.md or change the tests. Explain which failures are intentional exercises
> and whether the provided example, stub model and local HTTP connection work. Read
> EXERCISES.md and stop before the first exercise so I can brief you. Then work on one
> exercise at a time, show me the relevant test evidence and your changes, and stop
> for my review before continuing. Ask me to handle any interactive permission prompt.

Seeding happens automatically on first startup. The healthcheck stays unready
until COPY, indexes and the seed marker have committed. Pytest waits up to two
minutes for that marker. Subsequent starts reuse the named volume.

The target is under five minutes on a prepared laptop with a working internet
connection; downloads, Docker startup and corporate proxies can change that time.
The measured local checks and their limits are in `docs/VALIDATION.md`.

## Start here

```sh
pytest -q -m smoke
pytest -q tests/test_hour1_tools.py
pytest -q tests/test_hour2_harness.py
```

Open `EXERCISES.md`, the failing test and the corresponding function's docstring.
The only completed reporting tool is `totals_for_period`. Five tools are exercises.
The raw harness is mostly stubbed; the LangChain scaffold works with the example
tool and has an empty middleware list for you to fill.

## Register your server in Claude Code

Keep this running in a terminal with your Python environment activated:

```sh
python -m agentlab.mcp_server.server
```

Copy `.mcp.json.example` to `.mcp.json` in the repository root (`cp` on macOS,
`Copy-Item` in PowerShell), or use:

```sh
claude mcp add --transport http --scope project agentlab http://127.0.0.1:8765/mcp
```

Start a new Claude Code session from this repository, approve the project server
when prompted, and inspect `/mcp`. Ask: “Use agentlab to report total impressions,
spend and fill rate for August 2026.” After the exercises, compare July with August
and identify the advertiser furthest behind its August plan.

Claude Code calls this transport `http`; the Python adapter calls it
`streamable_http`; `FastMCP.run` uses `streamable-http`. These spellings are intentional.
See the [official registration documentation](https://code.claude.com/docs/en/mcp).

## Run the harnesses

```sh
agentlab-raw "Report August 2026 delivery totals."
agentlab-lc "Report August 2026 delivery totals."
```

The raw command works once its exercises are implemented. The LangChain command
loads tools over HTTP from your running MCP server. It works with the example
tool before the middleware exercises, but controls are deliberately incomplete.
Each command prints its trace path; inspect it with `agentlab-trace traces/<run-id>.jsonl`.
The summary counts all model invocations, including middleware summary calls.
Stub token counts are estimates; provider usage is labelled separately.

## Switch the model

`MODEL_PROVIDER=stub` is the default. `StubChatModel` emits real tool calls and
consumes the resulting observations. Its default scenario reports August totals.
It is deterministic, so changing the natural-language prompt does not change the
script: set `steps`, `repeat` or `scenario` in tests to exercise other behaviours.

The optional API path uses `MODEL_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`.
Put these in an ignored `.env`, using `.env.example` as the template, or set them
in your shell. `ANTHROPIC_MODEL` defaults to `claude-sonnet-4-6` and is configurable.
This optional path sends prompts and tool observations to Anthropic; use only the
synthetic lab data. No key is needed or fetched during normal tests.

The offline provider matrix uses the actual `ChatAnthropic` adapter with its HTTP
boundary mocked. That checks message and tool-call compatibility. A separate,
explicitly opted-in live test checks the API; it is skipped by default. To run it,
set `AGENTLAB_LIVE_TEST=1`, put the optional key in `.env`, then run `pytest -q -m live`.

LangChain installs the `langsmith` Python package transitively. The lab disables
its tracing environment switches before importing LangChain and requires no
LangSmith account, configuration or network calls.

## Data and boundaries

The warehouse spans 1 March 2025 to 31 August 2026: 60 publishers, 120 advertisers,
2,160 monthly plans and 1,515,240 fact rows. The seed has weekday/weekend variation,
a Q4 spike, declining fill for three publishers and one consistently underpacing
advertiser. All names and amounts are invented.

Dates are inclusive. Fill and pacing rates are fractions. Money uses one synthetic
currency. Comparisons belong in SQL. No tool response may contain over 500 rows.
The query exercise adds bounded paging with an optional cursor argument on the
same tool; it does not add another tool.

Postgres administration uses local user/password/database `agentlab`. Tools log
in as `agentlab_readonly`, with SELECT privileges and a two-second statement
timeout. Both exposed ports bind to loopback. This is a local workshop server;
remote deployment would require authentication and a different configuration.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Docker cannot connect | Open Docker Desktop or OrbStack, wait for its engine to be ready, then rerun `docker compose up -d`. |
| Port 55432 already in use | Stop the conflicting local lab, or set `AGENTLAB_DB_PORT=55433` in `.env` and rerun Compose and pytest. |
| Port 8765 already in use | Stop the other server or set `AGENTLAB_MCP_PORT=8766`; update both `.mcp.json` and `AGENTLAB_MCP_URL`. |
| Database is still starting | Run `docker compose ps` and `docker compose logs db`. Healthy means seed completion, not just an open port. |
| Claude Code cannot see tools | Keep the server terminal running; check `/mcp`, project approval, the `/mcp` URL and the activated Python environment. Restart Claude Code after copying its config. |
| No API key | Use the default stub. An empty middleware list or unfinished function is unrelated to API access. |
| MCP import error | Install the exact pins. MCP 2.2 is incompatible with adapter 0.3.2; see `docs/COMPATIBILITY.md`. |
| Pip blocked by a company proxy | Use your approved package mirror or pair with someone already set up. Do not disable TLS verification. |
| Windows scripts fail | Use a current PowerShell and an activated environment; the repository fixes LF endings for container scripts. |

Stop the lab with `docker compose stop`; data remains in its named volume. An
explicit seed recheck is `docker compose exec db python3 /opt/agentlab/seed.py`.
It is a no-op once the committed marker exists. Do not delete the volume to fix
an unfinished exercise.

## Facilitation and dependency notes

`FACILITATOR.md` contains full reference solutions; participants should leave it
closed. Acceptance tests are the shared specification. Dependencies declared in
`pyproject.toml` are exact pins, with a transitive `uv.lock` for repeatable resolution.
See `docs/COMPATIBILITY.md` for the package inspection and the necessary MCP deviation.
