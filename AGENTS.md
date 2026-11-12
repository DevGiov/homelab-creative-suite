# Agent Instructions — Creative Suite

> **Who may edit this file:** only the user and Claude. Antigravity (agy) must never edit any `AGENTS.md`.

Deployment and agent bridge for a suite of creative applications: a GPU workstation container that streams them (Sunshine, Moonlight Web), an MCP bridge to drive them (`mcp-server/`), and a second container that serves their browser (WASM) builds (`deploy/web/`).

- **The applications are submodules of other projects.** Do not modify them; they keep their own licenses. This repository owns `deploy/`, `mcp-server/`, `input-relay/` and the documentation.
- **This repository and the installation.** It describes the software, not the place where it runs: no addresses, host names or container ids of a real installation in scripts, configuration, tests, `README.md` or this file.
  - What depends on the installation is a site setting, read from `/etc/creative-suite/site.env` on each machine through `deploy/siteconf.py`; `deploy/site.example.env` documents every setting with invented values. `deploy/sunshine/sunshine.conf` and `deploy/web/nginx.conf` are templates the install scripts fill.
  - The install scripts stop before changing anything when a setting is missing. Keep that property when you add one, and add it to the example file and to the tests in `deploy/tests/`.
  - Tests use invented values (`.env-specific-allow` lists the accepted files).
  - `docs/` and `STREAMING_ARCHITECTURE.md` are the history of one installation and still name its machines: fix what you touch, do not rewrite them in bulk.
  - Instructions that are true for one installation only (which containers, how to deploy there) are in `AGENTS.local.md` in the repo root, gitignored and optional: read it if it exists.
- **Using the apps through the MCP tools:** read `MCP_TOOLS_GUIDE.md` first.
- **Validation:** `cd deploy && pytest && ruff check .`; `cd mcp-server && pytest && ruff check .`; `cd input-relay && pytest`.
