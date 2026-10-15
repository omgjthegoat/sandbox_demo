import json
import shutil
import tempfile
from pathlib import Path
import unittest

from assistant import load_assistant


BASE = Path(__file__).resolve().parent.parent
CASES = json.loads((BASE / 'tests' / 'conversations.json').read_text(encoding='utf-8'))


class SandboxConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.demo_base = Path(self.tmp.name)
        shutil.copytree(BASE / 'data', self.demo_base / 'data')
        (self.demo_base / 'leads').mkdir(parents=True, exist_ok=True)
        self.assistant = load_assistant(str(self.demo_base))

    def tearDown(self):
        self.tmp.cleanup()

    def run_case(self, case):
        session = case['name']
        last = None
        for msg in case['messages']:
            last = self.assistant.process(session, msg, transcript_reference=case['name'])
        return last

    def assert_case(self, case):
        resp = self.run_case(case)
        exp = case['expect']
        self.assertIsNotNone(resp)
        if exp.get('lead_saved'):
            self.assertTrue(resp.get('lead_record_path'), case['name'])
            path = Path(resp['lead_record_path'])
            self.assertTrue(path.exists())
            lead = json.loads(path.read_text(encoding='utf-8'))
            self.assertIn('routed_to', lead)
            if exp.get('route_team'):
                self.assertEqual(lead['routed_to']['team'], exp['route_team'])
            if exp.get('route_location'):
                self.assertEqual(lead['routed_to']['location'], exp['route_location'])
        else:
            self.assertFalse(resp.get('lead_record_path'))
        if exp.get('contains'):
            self.assertIn(exp['contains'].lower(), resp['reply'].lower())
        if exp.get('contains_any'):
            self.assertTrue(any(s.lower() in resp['reply'].lower() for s in exp['contains_any']))
        if 'needs_human' in exp:
            self.assertEqual(resp['needs_human'], exp['needs_human'])
        if exp.get('route_team') and not exp.get('lead_saved'):
            self.assertIsNotNone(resp.get('routed_to'))
            self.assertEqual(resp['routed_to']['team'], exp['route_team'])
        if exp.get('route_location') and not exp.get('lead_saved'):
            self.assertIsNotNone(resp.get('routed_to'))
            self.assertEqual(resp['routed_to']['location'], exp['route_location'])

    def test_scripted_conversations(self):
        for case in CASES:
            with self.subTest(case=case['name']):
                self.assert_case(case)


if __name__ == '__main__':
    unittest.main()
