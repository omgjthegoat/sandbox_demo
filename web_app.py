from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime, timezone
from fastapi.templating import Jinja2Templates

from assistant import load_assistant

app = FastAPI(title='Sandbox Shipping Demo')
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / 'templates'))
app.state.base_dir = str(Path(__file__).resolve().parent)
app.state.kb_bundle_path = str(Path(__file__).resolve().parent / 'data' / 'knowledge_base.json')
app.state.history = {}
app.state.quick_replies = ['Hours in DUMBO', 'Shipping quote', 'Mailbox pricing', 'Passport photos']
app.state.demo_scenarios = [
    {'label': 'Hours question', 'message': 'What are your hours in DUMBO on Sunday?'},
    {'label': 'Lead capture', 'message': 'I need help shipping a box.'},
    {'label': 'Quote request', 'message': 'How much for 1,000 flyers?'},
    {'label': 'Out of scope', 'message': 'Do you repair laptop screens?'}
]


def get_assistant():
    return load_assistant(app.state.base_dir)


def _history(session_id: str):
    return app.state.history.setdefault(session_id, [])


def _quick_replies():
    return getattr(app.state, 'quick_replies', [])


def _demo_scenarios():
    return getattr(app.state, 'demo_scenarios', [])


@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, 'index.html', {'title': 'Sandbox Shipping AI Front Desk Demo', 'quick_replies': _quick_replies(), 'demo_scenarios': _demo_scenarios()})


@app.post('/chat')
async def chat(payload: dict):
    assistant = get_assistant()
    session_id = payload.get('session_id', 'web')
    message = payload.get('message', '')
    history = _history(session_id)
    ts = datetime.now(timezone.utc).isoformat()
    history.append({'role': 'user', 'content': message, 'timestamp': ts})
    resp = assistant.process(session_id, message, transcript_reference='web-ui')
    history.append({'role': 'assistant', 'content': resp.get('reply', ''), 'timestamp': datetime.now(timezone.utc).isoformat()})
    return JSONResponse(resp)


@app.post('/kb')
async def save_kb(payload: dict):
    assistant = get_assistant()
    path = assistant.save_knowledge_base_bundle(payload)
    return JSONResponse({'ok': True, 'path': str(path)})


@app.get('/kb')
async def get_kb():
    assistant = get_assistant()
    return assistant.export_knowledge_base_bundle()


@app.get('/history/{session_id}')
async def get_history(session_id: str):
    return {'session_id': session_id, 'messages': _history(session_id)}
