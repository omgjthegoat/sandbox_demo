import json
import shutil
import tempfile
from pathlib import Path
import unittest

from assistant import load_assistant


BASE = Path(__file__).resolve().parent.parent


class KnowledgeBaseBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        shutil.copytree(BASE / 'data', self.base / 'data')
        (self.base / 'leads').mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exports_single_editable_bundle(self):
        assistant = load_assistant(str(self.base))
        bundle = assistant.export_knowledge_base_bundle()
        self.assertIn('services', bundle)
        self.assertIn('locations_hours', bundle)
        self.assertIn('routing_rules', bundle)
        self.assertEqual(bundle['locations_hours']['locations'][0]['name'], 'Park Slope')

    def test_imports_bundle_and_overrides_split_files(self):
        bundle = load_assistant(str(self.base)).export_knowledge_base_bundle()
        bundle['pricing']['shipping'][0]['price'] = '$99.99'
        bundle_path = self.base / 'data' / 'knowledge_base.json'
        bundle_path.write_text(json.dumps(bundle, indent=2), encoding='utf-8')
        assistant = load_assistant(str(self.base))
        self.assertEqual(assistant.kb['pricing']['shipping'][0]['price'], '$99.99')
        resp = assistant.process('s', 'How much are black and white copies?', transcript_reference='s')
        self.assertIn('$0.18/page', resp['reply'])


if __name__ == '__main__':
    unittest.main()
