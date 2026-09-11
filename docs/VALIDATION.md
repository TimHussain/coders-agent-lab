# Validation record

## Local checks — 11 September 2026

The lab was built and exercised on macOS with Python 3.12.8, OrbStack and
PostgreSQL 16.15. Data generation used Python inside the PostgreSQL container.

| Check | Observed result |
| --- | --- |
| Initial automatic seed | 1,515,240 fact rows in 22.65 seconds, including indexes |
| Dataset | 60 publishers, 120 advertisers, 2,160 plans; 1 March 2025–31 August 2026 |
| Synthetic patterns | Weekends lower than weekdays, Q4 spike, three declining publishers verified in SQL |
| Participant starter | 47 intentional failures, 12 passes, one optional live test skipped |
| Supplied setup gate | All 10 smoke checks pass |
| Facilitator guide | Its exact three solution blocks pass 59 tests; one optional live test skipped |
| MCP transport | Real HTTP server, discovery of exactly six tools, worked tool invocation |
| Framework harness | LangChain loads the tools through the local HTTP server and writes a local trace |
| Provider interface | Stub and actual ChatAnthropic adapter tested through the same harness; API boundary mocked |
| SQL controls | SELECT-only login privileges, 2s timeout, forced response limits, unsafe query refusal, bounded paging |
| Formatting/static checks | Ruff checks and formatting pass |

The exercise failures are required behaviour. They are not marked as xfail or
silently skipped. Setup failures remain visible as failures. The facilitator
reference uses the same tests as the starter in a separate temporary copy.

No real Anthropic call or credential was used. Windows instructions and LF script
endings are included, but Windows execution has not been observed. Installation
speed on an arbitrary cold machine depends on network access, Docker startup and
package mirrors; a universal under-five-minute result cannot be guaranteed from
one macOS run.

The agent-directed exercise addendum changed the participant instructions while
preserving the test suite byte-for-byte. MCP 1.30.0 is the documented compatibility
deviation; see `COMPATIBILITY.md` for the installed-package evidence.

## Published fresh-clone check

The public repository was cloned over HTTPS with credential helpers disabled into
a clean directory. A new Python virtual environment installed `.[dev]` using pip
with its package cache disabled. A separate Compose project on loopback port 55433
created a new named volume, so it did not reuse the original seeded database.

- The database became healthy and automatically loaded all 1,515,240 rows in
  **22.80 seconds**. Rechecking the seed completed in **0.01 seconds** without
  changing the committed marker or row count.
- The fresh participant checkout returned **47 intentional failures, 12 passes
  and one optional live test skipped**.
- Its setup gate returned **10 passes**.
- Its exact facilitator-guide solution blocks returned **59 passes and one
  optional live test skipped**, in a temporary copy with unchanged tests.
- Unauthenticated requests to the repository page and repository metadata
  returned HTTP 200; metadata reported `private=false`. The anonymous clone worked.
- GitHub's rendered README endpoint returned HTTP 200. Its headings, setup command
  block and kick-off prompt were checked, and the live GitHub page was visually
  inspected in a browser.
- The tracked file tree contains `.env.example` and does not contain `.env`,
  generated traces, Python caches or private programme material.

Docker and the PostgreSQL base image were already available on this machine for
this check. It proves a clean checkout, new Python environment and new database
volume; it is not a measurement of an entirely unprepared Windows or macOS laptop.
