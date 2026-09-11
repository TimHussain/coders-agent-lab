# Verified package surface — 11 September 2026

The initial requested stack installed `mcp==2.2.0` and
`langchain-mcp-adapters==0.3.1`, but importing `MultiServerMCPClient` failed:

```text
ImportError: cannot import name 'RequestContext' from 'mcp.shared.context'
```

Inspection of the installed adapter showed that it imports the MCP v1
`RequestContext`. MCP v2 replaces that interface. Installing adapter 0.3.2 resolved
to `mcp==1.30.0`; its package metadata explicitly requires `mcp>=1.24.0,<2.0.0`.
The starter therefore pins **MCP 1.30.0 and adapter 0.3.2**. This is a deliberate
deviation from the build brief's MCP 2.2 constraint, permitted by its instruction
to follow the installed packages when the requested stack does not match them.
It does not claim MCP v2 or the 2026-07-28 protocol revision.

Installed implementations/signatures inspected before authoring integration code:

| Package | Version | Surface used |
| --- | --- | --- |
| mcp | 1.30.0 | `FastMCP`, `.tool`, `.run(transport="streamable-http")`, stateless HTTP and typed output |
| langchain | 1.4.0 | `langchain.agents.create_agent`, async tool middleware, model/tool limits and summarisation |
| langchain-core | 1.6.2 | `BaseChatModel._generate`, `bind_tools`, AI/Tool messages, callbacks |
| langchain-mcp-adapters | 0.3.2 | `MultiServerMCPClient`, awaited `get_tools`, `streamable_http`, `handle_tool_errors=False` |
| langchain-anthropic | 1.7.2 | `ChatAnthropic.bind_tools`, request formatting and response conversion |

`MultiServerMCPClient` is not used as an async context manager. Its tools open
sessions per invocation, which fits the stateless local server. Client-side tool
error handling is disabled here so the middleware exercise owns recovery.

The pool extra is added to psycopg because binary alone does not install a pool.
SQLGlot is added for the query exercise's SQL parser: a keyword regex alone is
not a SQL permission boundary. `typing-extensions` supplies Python 3.11-compatible
typed dictionaries for the schema generator. Python in the PostgreSQL image uses
only its standard library plus `psql`, so seeding does not install Python packages.

The bootstrap command includes `[dev]` because pytest is a development dependency.
The brief also listed loose ranges; exact resolved pins implement its separate
requirement that every declared dependency be pinned.

First-party references used to check the integration:

- [MCP package and SDK migration information](https://pypi.org/project/mcp/)
- [LangChain MCP adapters package](https://pypi.org/project/langchain-mcp-adapters/)
- [LangChain MCP connection guidance](https://docs.langchain.com/oss/python/langchain/mcp)
- [LangChain agent middleware](https://docs.langchain.com/oss/python/langchain/middleware/overview)
- [Claude Code HTTP server registration](https://code.claude.com/docs/en/mcp)
- [Anthropic model identifiers](https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions)

The installed source and executed integration tests are the implementation evidence;
web documentation was used as a cross-check.
