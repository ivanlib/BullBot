# BullBot — Campus AI Knowledge Assistant for Sac State

[![CI](https://github.com/ivanlib/BullBot/actions/workflows/ci.yml/badge.svg)](https://github.com/ivanlib/BullBot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

BullBot answers student questions about transfer credits, financial aid, and degree
planning, and backs up each answer with a citation to the source document. When the
documents don't clearly support an answer, it points the student to Academic Advising or
the Financial Aid office instead of guessing. It handles English and Spanish and screens
out personal information and off-topic questions.

I built it to get hands-on with Retrieval-Augmented Generation (RAG) on AWS: a Bedrock
Knowledge Base for retrieval, Titan embeddings in an OpenSearch Serverless vector store,
Bedrock Guardrails for safety, and a small FastAPI + vanilla-JS web app on top. It started
at the YouthTechSacState Kiro Hackathon and I've kept working on it as a personal project.

It runs in two modes:

- **Demo mode** — answers come from a local file of prepared examples. No AWS account or
  credentials needed, so anyone can clone the repo and try the UI.
- **Live mode** — answers come from Amazon Bedrock using your own AWS resources.

> The knowledge-base documents in `docs/` are made-up samples for demonstration, not real
> Sac State policy. BullBot is a personal project, not affiliated with or endorsed by the
> university, and isn't a substitute for talking to an advisor.

## Screenshots

Welcome screen (demo mode):

![BullBot welcome screen](docs/screenshots/welcome.png)

A grounded answer with a table and citations:

![BullBot conversation with citations](docs/screenshots/conversation.png)

## How it works

```
                 Browser (chat UI, Markdown + citations)
                                 |  HTTP /api/chat
                                 v
                 FastAPI backend  (web/app.py)
                                 |
                 Shared chat core (web/bullbot_core.py)
                        |                         |
             demo mode (offline)          live mode (AWS)
                        |                         |
     web/demo_responses.json         Amazon Bedrock
     (prepared sample answers)         RetrieveAndGenerate + Guardrail
                                               |
                                   Knowledge Base (Titan V2 embeddings)
                                        |               |
                                 S3 source docs   OpenSearch Serverless
```

The web backend and the command-line client (`scripts/bullbot_chat.py`) call the same
function, `bullbot_core.ask()`. That function checks `BULLBOT_DEMO_MODE`: when it's set, it
returns a prepared answer from `web/demo_responses.json`; otherwise it calls Bedrock. There
is only one inference path, and no local AI models — live inference happens on Bedrock.

The frontend is plain HTML/CSS/JS with no build step. Markdown is rendered with `marked`
and sanitized with `DOMPurify`, both loaded from a CDN. The chat supports conversation
history within a session, tables and links, a loading indicator, error messages, and a
"New chat" button, and works on desktop and mobile.

Design notes — chunking strategy, the vector index mapping, guardrail configuration, agent
instructions, and the original build plan — are in [`docs/specs/`](docs/specs/).

## Technology stack

| Layer | Technology |
|-------|------------|
| Backend | Python, FastAPI, uvicorn |
| Frontend | HTML / CSS / vanilla JS; `marked` + `DOMPurify` via CDN |
| Retrieval | Amazon Bedrock Knowledge Bases |
| Generation | Anthropic Claude on Amazon Bedrock (via inference profile) |
| Embeddings | Amazon Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`, 1024-dim) |
| Vector store | Amazon OpenSearch Serverless (VECTORSEARCH) |
| Source storage | Amazon S3 |
| Safety | Amazon Bedrock Guardrails (PII, denied topics) |
| Tests / CI | pytest, GitHub Actions |

## Quick start (demo mode, no AWS)

Clone the repo, create a virtual environment, install the web dependencies, and start the
server with demo mode on. From the project root:

```powershell
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r web/requirements.txt

$env:BULLBOT_DEMO_MODE = "1"
python -m uvicorn app:app --app-dir web --host 127.0.0.1 --port 8000
```

```bash
# macOS / Linux
python -m venv .venv
source .venv/bin/activate
pip install -r web/requirements.txt

export BULLBOT_DEMO_MODE=1
python -m uvicorn app:app --app-dir web --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and you'll see a "Demo Mode" badge in the header. Stop the
server with `Ctrl+C`.

In demo mode BullBot only answers the prepared questions (transfer credits, Cal Grant B,
Data Science minor, a Spanish example, plus PII and off-topic cases); anything else gets a
short fallback message. The offline PII and off-topic checks are simple keyword matches
meant to illustrate the behavior — they are not the real Bedrock Guardrails and shouldn't
be relied on.

## Running tests

Tests run entirely in demo mode: no AWS credentials or network, and they assert that no AWS
client is ever created.

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

## Live mode (Amazon Bedrock)

Live mode uses your own AWS account; the repo doesn't include or share any AWS resources.
You'll need:

- An AWS account with Bedrock model access enabled for an Anthropic Claude model and Amazon
  Titan Text Embeddings V2.
- Permission to create the resources below, plus `bedrock:RetrieveAndGenerate` and
  `bedrock:ApplyGuardrail` at runtime.
- Credentials from your own AWS CLI session or profile (never committed). The app reads
  configuration from environment variables only — see `web/.env.example`.

Running these resources costs money; `scripts/99_teardown.py` removes them when you're done.

### Provision the resources

The `scripts/` folder has idempotent `boto3` scripts. `scripts/config.py` holds the region
and resource names. Run them from the project root, in this order (step 3 creates the IAM
role that step 2's data-access policy needs):

```bash
pip install -r scripts/requirements.txt
python scripts/01_create_s3_source.py                                    # S3 bucket + upload docs/
python scripts/03_create_kb_role.py                                      # IAM role for the KB
python scripts/02_create_vector_store.py <KB_ROLE_ARN>                   # OpenSearch Serverless
python scripts/04_create_knowledge_base.py <KB_ROLE_ARN> <COLLECTION_ARN>  # KB + ingest docs
python scripts/05_create_guardrail.py                                    # PII + topic guardrail
python scripts/verify_retrieval.py <KB_ID>                               # sanity-check retrieval
```

Scripts `06_create_agent.py` and `07_invoke_demo.py` build a classic Bedrock Agent. They're
kept for reference, but BullBot doesn't need them: it calls `RetrieveAndGenerate` directly,
which is the current recommended approach (Bedrock Agents "classic" is in maintenance mode
and closed to new customers). See [`docs/specs/tasks.md`](docs/specs/tasks.md) for details.

### Start in live mode

Set the IDs from the script output (KB ID from step 4, guardrail ID from step 5), then run
the server from the project root:

```powershell
# Windows (PowerShell)
$env:BULLBOT_KB_ID = "your-kb-id"
$env:BULLBOT_GUARDRAIL_ID = "your-guardrail-id"
$env:BULLBOT_GUARDRAIL_VERSION = "1"
$env:AWS_REGION = "us-east-1"
python -m uvicorn app:app --app-dir web --host 127.0.0.1 --port 8000
```

### Environment variables

| Variable | Meaning | Example |
|----------|---------|---------|
| `BULLBOT_DEMO_MODE` | `1` turns on offline demo mode | `1` |
| `BULLBOT_KB_ID` | Knowledge Base ID (live mode) | `your-kb-id` |
| `BULLBOT_GUARDRAIL_ID` | Guardrail ID (live mode) | `your-guardrail-id` |
| `BULLBOT_GUARDRAIL_VERSION` | Guardrail version, not `DRAFT` (live mode) | `1` |
| `AWS_REGION` | AWS region (live mode) | `us-east-1` |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `503 Server not configured` | Set `BULLBOT_KB_ID` + `BULLBOT_GUARDRAIL_ID` for live mode, or `BULLBOT_DEMO_MODE=1` for demo mode. |
| `502 could not reach knowledge service` | Live mode only: AWS credentials likely expired — refresh them. The server log has the detail. |
| `504 took too long` | Bedrock was slow; retry. The request timeout is 60s (`REQUEST_TIMEOUT_SECONDS` in `web/app.py`). |
| Answers show raw `*asterisks*` | The Markdown libraries (loaded from a CDN) were blocked by the network. |
| Port 8000 already in use | Another process has it; use `--port 8001`, or wait for a closing socket to clear. |

## Notes on resource use

- Run a single server; don't use `--reload` (its file watcher isn't needed here).
- No local models are loaded — inference is on Bedrock, so the server stays small
  (around 80 MB RAM when idle).
- The backend caps input at 2000 characters, times out requests at 60s, and bounds its
  in-memory session store.
- `.vscode/settings.json` keeps `.venv`, `__pycache__`, and logs out of editor indexing.

## Limitations

- The bundled documents are made-up samples, not real policy. Answers reflect those samples
  and shouldn't be used for actual decisions.
- Demo-mode PII and off-topic screening is keyword-based and only approximates the real
  Bedrock Guardrails used in live mode.
- Demo mode only answers the prepared questions; everything else returns a fallback.
- Live mode depends on your AWS account, model access, and credentials, and incurs cost.
- BullBot is a learning project, not an official advising tool.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Ivan Librado.
