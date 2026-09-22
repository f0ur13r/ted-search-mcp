# TED Search MCP app

A minimal, read-only MCP server that lets ChatGPT search the public [TED Search API v3](https://api.ted.europa.eu/swagger-ui/index.html). It has one tool, `search_ted_notices`, and needs no TED API key, database, queue, or OpenAI API key.

## Tool

`search_ted_notices(date_from, date_to, country?, cpv_codes?, free_text_query?, max_results=50)`

- Dates are inclusive and use `YYYY-MM-DD`.
- `country` is a three-letter TED place-of-performance code such as `DEU`.
- CPV entries accept 2–8 digits and an optional trailing wildcard, such as `32420000` or `72*`.
- `free_text_query` is treated as a literal TED full-text phrase.
- `max_results` is 1–250. This intentionally uses a single API page to keep scheduled runs bounded.

The result includes the title, buyer, publication date, deadlines, notice type, CPVs, places of performance, description, estimated value/currency, procedure ID, publication number, and TED URL. Localized text prefers German, then English, then the first available language.

## Run locally

Python 3.11+ is recommended.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python server.py
```

That starts the MCP server over stdio. For local HTTP testing:

```bash
uvicorn server:app --host 127.0.0.1 --port 8000
```

The Streamable HTTP MCP endpoint is `http://127.0.0.1:8000/mcp`.

Run the tests:

```bash
python -m unittest discover -s tests -v
```

## Deploy with no extra infrastructure

Deploy this directory as a Docker web service on any small container host (Render, Railway, Fly.io, Cloud Run, or an existing server). The included `Dockerfile` is self-contained. The platform must set `PORT`; most hosts do this automatically.

Example Docker commands:

```bash
docker build -t ted-search-mcp .
docker run --rm -p 8000:8000 -e PORT=8000 ted-search-mcp
```

Terminate TLS at the hosting platform. Your ChatGPT connection URL will be:

```text
https://YOUR-HOST/mcp
```

No secrets are required. If you make the service public, consider adding host-level rate limiting because the endpoint proxies an open third-party API.

### Render Free

1. Push this directory to a GitHub repository.
2. In Render, choose **New → Blueprint** and connect that repository.
3. Render detects `render.yaml`. Review the `ted-search-mcp` service and deploy it.
4. Wait for the service status to become **Live**.
5. Your MCP endpoint is the service URL followed by `/mcp`, for example `https://ted-search-mcp.onrender.com/mcp`.

The included Blueprint selects Render's Free web-service plan. Free services can sleep after inactivity, so the first call after a quiet period can be slower.

## Connect it to ChatGPT

1. Deploy the service at a stable public HTTPS URL.
2. In ChatGPT, open **Settings → Apps** (or your workspace's app controls) and create a custom MCP app.
3. Set the MCP server URL to `https://YOUR-HOST/mcp`. Choose no authentication.
4. Publish/enable the draft app for yourself or the intended workspace role.
5. Start a new conversation, enable the app, and ask: `Search TED notices published today in Germany for firewall opportunities.`

Custom-app availability and publishing controls depend on the ChatGPT plan and workspace settings. For a managed workspace, an admin may need to allow custom apps and enable the published draft.

## Scheduled ChatGPT task prompt

After the app is connected and can be called in a normal conversation, create a recurring task in ChatGPT with this prompt (adjust the schedule separately):

```text
Use the TED Search app and call search_ted_notices for notices published since the previous run, with country DEU and max_results 250. Search broadly: do not apply a free-text or CPV filter unless needed to stay within the result limit.

Screen every returned notice semantically for network-security relevance, including firewalls, VPN, remote access, SASE/SSE/ZTNA, NAC, segmentation, IDS/IPS, DNS security, secure web gateways, and network-security management. Score each opportunity from 0 to 100 and return only scores of 60 or more.

For each result show buyer, title, publication number/date, submission deadline, CPV, estimated value, relevant technology, score, concise reasoning, blockers, recommended next action, and TED link. State clearly when no relevant notices are found. If total_matching_count exceeds returned_count, warn that the run was truncated and recommend narrower searches.
```

Scheduled tasks can use connected apps only where that app/task combination is supported for the account and workspace. Verify the first run manually before relying on it.

## Design choices

- Read-only and unauthenticated: TED Search itself requires no API key.
- One bounded tool and one API request per call.
- Standard-library TED client; only the official MCP package and server runner are dependencies.
- Inputs are validated and safely converted to TED expert-search syntax.
- No persistence: the task prompt owns the screening logic and run window.

For exact incremental windows, have the scheduled task pass the last successful run date explicitly. Dates are inclusive, so deduplicate by `publication_number` if runs overlap.
