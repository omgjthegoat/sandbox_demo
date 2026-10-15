import json
import shutil
import tempfile
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from web_app import app


BASE = Path(__file__).resolve().parent.parent


class WebUITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        shutil.copytree(BASE / 'data', self.base / 'data')
        (self.base / 'leads').mkdir(parents=True, exist_ok=True)
        app.state.base_dir = str(self.base)
        app.state.kb_bundle_path = str(self.base / 'data' / 'knowledge_base.json')
        app.state.history = {}
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def test_home_page_loads(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Sandbox Shipping AI Front Desk Demo', r.text)
        self.assertIn('Conversation history', r.text)
        self.assertIn('Bundle editor', r.text)
        self.assertIn('Quick replies', r.text)
        self.assertIn('Demo scenarios', r.text)

    def test_chat_endpoint_returns_response(self):
        r = self.client.post('/chat', json={'session_id': 'web1', 'message': 'What are your hours in DUMBO on Sunday?'})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['stage'], 'faq')
        self.assertIn('DUMBO', data['reply'])

    def test_chat_endpoint_returns_history(self):
        self.client.post('/chat', json={'session_id': 'web2', 'message': 'What are your hours in DUMBO on Sunday?'})
        r = self.client.get('/history/web2')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data['messages']), 2)
        self.assertEqual(data['messages'][0]['role'], 'user')
        self.assertEqual(data['messages'][1]['role'], 'assistant')
        self.assertIn('timestamp', data['messages'][0])
        self.assertIn('timestamp', data['messages'][1])

    def test_kb_editor_saves_bundle(self):
        payload = {
            'services': {'business_name': 'Sandbox Shipping'},
            'pricing': {'shipping': [{'item': 'test', 'price': '$1.00'}]},
            'locations_hours': {'locations': []},
            'policies': {},
            'routing_rules': {'default_location': 'Park Slope'},
        }
        r = self.client.post('/kb', json=payload)
        self.assertEqual(r.status_code, 200)
        bundle_path = self.base / 'data' / 'knowledge_base.json'
        self.assertTrue(bundle_path.exists())
        saved = json.loads(bundle_path.read_text(encoding='utf-8'))
        self.assertEqual(saved['pricing']['shipping'][0]['price'], '$1.00')


if __name__ == '__main__':
    unittest.main()
