# Direct the agent. Review the result.

You are not writing this code. You are deciding what gets written, and reviewing it.
Work one tool at a time and make your agent stop after each so you can read what it did.
If it is heading the wrong way, interrupt it — do not let it finish out of politeness.

Brief Claude Code in ordinary language. Ask it to run the commands, show you the
evidence and stop for review. You do not need to type commands or hand-write code.
Keep `FACILITATOR.md` closed. Tell your agent to leave the tests unchanged: they define done.

## Start the session

Use the kick-off prompt in the README. Have the agent establish that the supplied
example and infrastructure checks pass before it changes anything. Expected exercise
failures are useful; a broken database or undiscoverable server is a setup problem.
Make the agent explain which kind of failure it found.

## Hour one: useful questions, trustworthy answers

**Goal:** Direct your agent to build a reporting interface that answers real questions
without exposing unnecessary data or leaving arithmetic to the model.

**Acceptance:** Ask the agent to run `pytest -q tests/test_hour1_tools.py` after each
tool, explain the relevant results and distinguish the remaining exercises.

### 1. Understand the worked example

**The question:** “How much delivery and spend did we have in August, and how much
available inventory did we fill? Can I look at Italy alone?”

**A good result:** One small answer with impressions, clicks, spend, revenue and fill
rate, identifying the requested period, country filter and generation time.

**What to refuse:** Raw delivery exports, unrelated countries, reversed dates or
claims that an empty result demonstrates a real-world business outcome.

**What to check:** The database calculates the totals. Fill rate divides total
impressions by total requests; it does not average row percentages. The tool's
description tells the model when to use it. This example already works: ask the
agent to explain it before changing anything elsewhere.

### 2. See where spend is concentrated

**The question:** “Which publishers account for most of our spend this month?”

**A good result:** A short ranked list, ten publishers by default, with each publisher's
name, spend, impressions and fill rate. Include the period and generation time;
never return more than 500 rows.

**What to refuse:** An unbounded export, invalid list sizes or individual delivery
records when the question needs a summary.

**What to check:** The agent aggregates before ranking and limiting. Ties have a
stable order. Fill rates are weighted correctly. Review the result and relevant
passing assertions before asking the agent to move on.

### 3. Explain what changed

**The question:** “How did August compare with July? Did spend, delivery and fill
rate go up or down?”

**A good result:** One compact comparison with absolute and relative spend change,
impression change and fill-rate change. Identify both periods and generation time.

**What to refuse:** Two separate totals that leave the model to subtract, ambiguous
periods or a percentage that divides by zero.

**What to check:** The database computes current minus prior in one statement. The
direction is correct. Relative change is a fraction and becomes null when prior
spend is zero. Fill-rate change compares weighted rates. The description makes clear
that this tool owns the comparison.

### 4. Find advertisers behind plan

**The question:** “Which advertisers are furthest behind their monthly budget?”

**A good result:** A bounded list with advertiser, actual spend, planned spend,
pacing ratio and variance, ordered from lowest pacing. Include the full month and
generation time. Advertisers with a plan and no delivery still belong in it.

**What to refuse:** Invented budgets, invalid months, more than 500 rows or partial
month figures presented as full-month performance.

**What to check:** Each monthly budget is counted once when joined to delivery.
Actual spend is aggregated first. Zero-plan and no-delivery cases are explicit.
The synthetic advertiser behind plan appears for the right reason.

### 5. Allow a limited follow-up question

**The question:** “My reporting question is not covered by the standard tools.
Can I inspect a small result without changing the warehouse?”

**A good result:** A read-only, ordered page of at most 500 rows, a continuation
cursor when more permitted rows exist and a generation time. Arbitrary queries
have no invented single reporting period. The total result is also bounded.

**What to refuse:** Writes, schema changes, grants, unbounded queries, system tables,
external access, unsafe functions, multiple statements or altered and expired cursors.

**What to check:** Ask the agent to show the refusal tests and explain why keyword
checking alone is insufficient. The role is read-only, queries have a timeout, and
the server imposes its own limit even when a caller requests more. Paging preserves
order without duplicate or missing rows.

### 6. Make the boundaries visible

**The question:** “Before I rely on this assistant, what will it refuse to expose or do?”

**A good result:** A short timestamped refusal policy covering writes, credentials,
personal data, unbounded exports, system tables and external access. It invents no
reporting dates for a policy statement.

**What to refuse:** Claims that a written policy enforces itself, or promises beyond
what the code and database actually prevent.

**What to check:** Each stated boundary has a control or follows from the deliberately
synthetic data. Ask the agent to distinguish these cases.

**Done looks like:** Ask your agent to start and register the server in your Claude
Code session, then ask a multi-step reporting question. The hour-one tests pass,
the tools are discoverable over HTTP, and you can explain the tool-design decisions.

## Hour two: control the work, even when the model changes

**Goal:** Direct your agent to build a harness whose limits, recovery and context
remain under your control independently of its model provider.

**Acceptance:** Ask the agent to run `pytest -q tests/test_hour2_harness.py`, show the
evidence for the current exercise and stop for review before the next one.

### 1. Carry a question through to an answer

**The question:** “Can the assistant look up the figures it needs, read what came
back and give me a final answer?”

**A good result:** A visible sequence of model calls, tool calls and observations,
ending in an answer grounded in the returned evidence.

**What to refuse:** Invented observations, answers before required tools run, or a
loop that continues after the model finishes.

**What to check:** Every result matches its call identifier. The model receives the
result before deciding again. Ask the agent to demonstrate the deterministic
scenario and the terminal-condition test.

### 2. Set a budget and recover from trouble

**The question:** “Can I limit the work this assistant does and still get a clear
explanation if a tool fails or the budget runs out?”

**A good result:** Separate limits on model turns and tool calls, a stated stopping
reason, and actionable error observations that let the model recover.

**What to refuse:** Endless retries, work beyond budget, private exception details
or execution of a tool the harness denies.

**What to check:** Limits are checked before each call, including calls within a
batch. Zero remaining calls is handled cleanly. The guardrail runs before execution.
Errors preserve call identifiers and suggest a useful next action.

### 3. Keep enough context without carrying everything

**The question:** “After a long exchange, can the assistant remember useful context
without sending the entire history every time?”

**A good result:** A labelled, shorter account of older turns with recent messages
intact. The trace records compaction and the reduction in size.

**What to refuse:** Lost recent evidence, a result separated from its tool call,
or old conversation content promoted into a system instruction.

**What to check:** The loop actually uses compaction above the threshold, reduces
token estimates and preserves the required recent messages. Ask the agent to lower
the threshold and show what information is lost.

### 4. Reproduce the controls in LangChain

**The question:** “Can a framework give me the same controlled behaviour while using
the reporting server I just built?”

**A good result:** Tools discovered over local HTTP, with summarisation, model and
tool limits, error recovery and a guardrail. Every control has acceptance evidence.

**What to refuse:** A duplicate tool set that bypasses your server, hosted tracing,
hidden paid dependencies or an unhandled recursion error presented as a stopping rule.

**What to check:** Ask the agent to add one control at a time. Middleware works with
asynchronous MCP calls. Compare successful and budget-exhausted traces with the raw harness.

### 5. Change a setting and explain the effect

**The question:** “What changes when I lower the work budget, shrink the context or
switch the model?”

**A good result:** A small local trace summary of model calls, tool calls and token
usage, with an explanation tied to the changed setting. The same harness passes
the stub and Anthropic adapter contract tests.

**What to refuse:** A harness rewritten for each provider, estimated tokens described
as billed usage, or a mocked test presented as live API proof.

**What to check:** Ask the agent to open the JSONL trace and reconcile its summary.
The offline matrix uses the real Anthropic adapter with its network boundary mocked.
The live test stays skipped without explicit opt-in and a key; the session does not
rely on it.

**Done looks like:** Hour-two tests pass, each run ends with a reason and a local
trace explains the work. You can direct a change and judge its consequences without
writing the implementation yourself.

## When the agent gets stuck

Ask it to read the failing assertion and docstring together and explain the mismatch.
Ask it to inspect an installed package before changing an unfamiliar API call.
Narrow the brief to one result. If it starts weakening tests or adding unrelated
machinery, interrupt and redirect it. Use a partner to review the contract; ask the
facilitator before opening solutions.

Keep the test output, one useful trace and one decision you can explain. Green tests
demonstrate these workshop contracts; they do not establish production readiness or
a measured business outcome.
