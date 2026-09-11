# LangChain — what you did not have to build

**Onetag Coders Track · Practice 1 · reference to keep**

In the second hour you built an agent harness by hand: the loop, a stopping rule, error recovery,
context management, a guardrail, and an interface thin enough to change the model behind it.

This is what LangChain already provides for that same job, and what else is in the box if you go
looking. It is written to be read after the session rather than during it.

**Two things worth saying first.** LangChain is an open-source Python library — you install it into
your own project and it runs wherever your code runs. No account, no hosted service, nothing leaving
your environment. LangSmith, which appears throughout their documentation, is a separate hosted
product for tracing; it is optional, and we did not use it.

And the reason for building it by hand first: you now know what each of these pieces does.
Configuring something you understand is a different activity from importing something you do not.

---

## The core

`create_agent` is the harness. LangChain's own documentation describes it as *"a minimal, highly
configurable harness"* — the same word we used all morning, which is a fair sign the mental model
transfers.

Everything else attaches to it as **middleware**: composable layers wrapped around the loop. There
are six points you can hook into.

`before_agent` · `before_model` · `wrap_model_call` · `wrap_tool_call` · `after_model` · `after_agent`

If you can say where in the loop your concern belongs, you can write middleware for it.

---

## What you wrote by hand, and what already exists

| Your layer | The equivalent | What it does |
| --- | --- | --- |
| The loop | `create_agent` | The harness itself — model, tools, and the cycle between them |
| Context economy | `SummarizationMiddleware` | Summarises older turns as the window fills, keeps the recent ones |
| The stopping rule | `ToolCallLimitMiddleware`, `ModelCallLimitMiddleware` | Caps calls per run or per thread, with configurable exit behaviour |
| Error recovery | Tool error handling | Turns an exception into a message the model can act on, rather than a crash |

---

## The rest of the middleware

- **`ContextEditingMiddleware`** — drops older tool results once a token threshold is crossed while keeping the recent ones. This is what saves you when a tool returns ten thousand rows
- **`HumanInTheLoopMiddleware`** — pauses the run so a person can approve, edit or reject a tool call before it executes. Risk tiers enforced in code rather than in a policy document
- **`PIIMiddleware`** — detects personal data and redacts, masks, hashes or blocks it before it reaches the model
- **`ToolRetryMiddleware`** — exponential backoff on failed tool calls
- **`ModelRetryMiddleware`** — the same for failed model calls
- **`ModelFallbackMiddleware`** — automatic fallback to another model when the primary one fails

---

## Changing the model

- **`init_chat_model`** — one call, any provider. This is the piece that makes the model swappable, and it is the same idea as the interface you built
- **`ChatAnthropic`**, **`ChatOpenAI`**, **`ChatOpenRouter`** and the rest — same interface, different provider
- **`content_blocks`** — unified access to reasoning traces, citations and provider built-in tools, so provider-specific handling does not leak into your agent code

---

## Tools you do not have to write

Worth a look before you build something from scratch. Most of these have an open-source client
library; some of the services behind them are commercial, and that distinction is worth checking
case by case.

**Search** — Tavily, Exa, Perplexity, Google. Tavily and Exa have free tiers large enough to build
against. Comfortably the most-used category.

**Databases and SQL** — SQL toolkits, and Google's **MCP Toolbox for Databases** (Apache 2.0, self-hosted),
which speaks PostgreSQL, MySQL, SQL Server, Oracle, MongoDB, Redis, **Elasticsearch**, ClickHouse,
Snowflake, BigQuery and more. It is a configuration file rather than a codebase, and it is directly
relevant to connector work — worth twenty minutes of anyone's time.

**Documents and web** — Firecrawl and the scraping tools for extraction and crawling, plus loaders
for the usual document sources.

**Productivity** — Gmail and Calendar toolkits, browser automation.

**Aggregators** — Composio, if you want several hundred integrations behind one interface.

**MCP** — `langchain-mcp-adapters` and `MultiServerMCPClient`. This is how the server you built in
the first hour plugs into an agent you build in the second: over HTTP, with bearer headers if you
have put auth in front of it.

---

## LangGraph, underneath

`create_agent` is built on LangGraph. You do not need it for a straightforward agent, but it is what
you reach for when the route needs to be the same every time rather than decided by a model:

- **Persistence and checkpointing** — state survives a restart
- **Durable execution** — long-running work resumes rather than starting over
- **Explicit state and branching** — a defined path, not a model's choice
- **Human-in-the-loop** — pause, inspect, resume
- **Time travel** — rewind to an earlier state and take a different branch
- **Streaming** — tokens and intermediate steps as they happen

---

## What is worth tuning

If you want to understand a layer properly, change its setting and watch what happens. That is
faster than reading about it.

| Component | What you can change | What you will see |
| --- | --- | --- |
| Summarisation | Token threshold, how many recent messages to keep | Lower it and answers get vaguer — memory loss you caused deliberately |
| Context editing | Threshold, and what counts as old | Large tool results leave the context earlier |
| Tool call limits | Per run, per thread, and the exit behaviour | It gives up rather than hanging — and either does or does not tell you why |
| Human in the loop | Which tools need approval, whether edits are allowed | Your risk tiers, enforced rather than documented |
| PII | Strategy per data type — redact, mask, hash or block | What the model is permitted to see at all |
| Retries | Maximum attempts, backoff curve | Flaky tools stop killing runs |
| Model fallback | The order models are tried in | An outage degrades instead of failing outright |
| Tool errors | What message goes back to the model | The difference between a crash and a recovery |

---

## On versions

LangChain reached v1 during 2026 and the public API moved with it — `create_agent` replaced the older
`create_react_agent`, the namespace narrowed, and legacy functionality moved to `langchain-classic`.
Anything you find in an older tutorial may not match what you have installed.

The reliable habit, and a good instruction to give your agent: **install it, read the installed
package, and write against what is actually there.**

---

## On LangSmith

It comes up constantly in the documentation, so it is worth being clear about what it is. LangSmith
is LangChain's hosted platform for tracing, datasets and evaluation — useful, and genuinely the part
people skip. It is also a hosted service, which means prompt and response content leaves your
environment.

That is a decision for Onetag rather than for any individual, and there are self-hosted alternatives
if the answer is no. We will come back to it properly in the evaluation and monitoring session,
where it belongs.

For this session you built your own tracing, which is why you already know what it would be doing.
