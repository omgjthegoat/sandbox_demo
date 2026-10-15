# Sandbox Shipping AI Front Desk Demo

Portfolio demo for a **fictional** Brooklyn business called Sandbox Shipping.

## What it demonstrates
- Knowledge-grounded front desk assistance
- FAQ answering from editable knowledge-base files
- Lead intake and routing
- Human escalation when the answer is unknown or out of scope
- Lead records saved as JSON for CRM handoff simulation

## Fictional business
Sandbox Shipping is fictional. The addresses, phone numbers, prices, and policies in this demo are made up for portfolio purposes.

## Features
- Editable knowledge base as split files or a single bundle
- CLI chat demo
- FastAPI web UI
- Lead routing by service type and location
- Quote requests routed instead of priced
- Human escalation for unknown or out-of-scope requests
- Saved lead JSON handoff files

## Setup
```bash
cd sandbox_demo
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn jinja2
```

## Run
CLI:
```bash
python3 demo_cli.py
```

Web UI:
```bash
uvicorn web_app:app --reload
```

## Tests
```bash
python3 -m unittest discover -s tests -v
```

## Architecture
- `assistant.py` — core assistant logic and routing
- `demo_cli.py` — terminal demo
- `web_app.py` — FastAPI endpoints
- `templates/index.html` — chat UI and KB editor
- `data/knowledge_base/` and `data/knowledge_base.json` — editable KB sources
- `leads/` — generated lead JSON files
- `tests/` — scripted conversation and UI tests

## Screenshots
- `screenshot.png` — captured from the local web UI

## Test results
- `python3 -m unittest discover -s tests -v` → OK

## Notes
- Pricing and hours are sample data for the demo.
- Quote-based jobs are routed, not priced.
- The assistant must never invent prices, hours, or policies.
