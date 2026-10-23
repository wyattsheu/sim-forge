"""Exercise real byte transport, PNG validation and non-overwrite behavior."""
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / 'tools/diaggen_support/save_imagegen_result.js'


class ImagegenPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "run 'quoted' $(touch SHOULD_NOT_EXIST)"
        self.root.mkdir()
        self.target = self.root / 'revisions/revision_0000/cleanup/attempt_1.png'
        state = {'run_root': str(self.root), 'paths': {
            'image_cleanup_attempt_1_path': str(self.target),
            'image_cleanup_attempt_2_path': str(self.target.with_name('attempt_2.png'))}}
        (self.root / 'state.json').write_text(json.dumps(state))
        self.node = shutil.which('node')
        self.assertIsNotNone(self.node, 'Node is required to test the actual functions.exec helper')

    def invoke(self, payload, *, target=None):
        request = {'result': payload, 'root': str(self.root),
                   'target': str(target or self.target), 'python': sys.executable,
                   'helper': str(HELPER)}
        script = """
const fs = require('node:fs');
const cp = require('node:child_process');
const req = JSON.parse(fs.readFileSync(0, 'utf8'));
global.tools = {exec_command: async ({cmd}) => {
  const r = cp.spawnSync('/bin/bash', ['-c', cmd], {encoding:'utf8',maxBuffer:1024*1024});
  return {exit_code:r.status,output:(r.stdout||'')+(r.stderr||'')};
}};
(async () => {
  const save = eval(fs.readFileSync(req.helper,'utf8'));
  try { console.log(JSON.stringify(await save(req.result,req.root,req.target,req.python))); }
  catch (e) { console.error(e.message); process.exitCode=1; }
})();
"""
        return subprocess.run([self.node, '-e', script], input=json.dumps(request),
                              text=True, capture_output=True, timeout=90)

    @staticmethod
    def png(size=(16, 16)):
        stream = io.BytesIO()
        # Deterministic noisy fixture exercises transport above the OS argument limit.
        image = Image.effect_noise(size, 100).convert('RGB')
        image.save(stream, format='PNG')
        return stream.getvalue()

    @staticmethod
    def result(data):
        return {'image_url': 'data:image/png;base64,' + base64.b64encode(data).decode()}

    def test_large_png_is_complete_and_byte_identical(self):
        data = self.png((600, 600))
        self.assertGreater(len(data), 128 * 1024)
        result = self.invoke(self.result(data))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), data)
        self.assertEqual(json.loads(result.stdout)['sha256'], hashlib.sha256(data).hexdigest())
        self.assertLess(len(result.stdout), 500)
        self.assertFalse((ROOT / 'SHOULD_NOT_EXIST').exists())

    def test_mcp_image_block_is_saved(self):
        data = self.png()
        payload = {'content': [{'type': 'image', 'mimeType': 'image/png',
                                'data': base64.b64encode(data).decode()}]}
        result = self.invoke(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), data)

    def test_truncated_valid_base64_cannot_become_candidate(self):
        result = self.invoke(self.result(self.png()[:24]))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.target.exists())

    def test_existing_candidate_is_never_overwritten(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'original')
        result = self.invoke(self.result(self.png()))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_bytes(), b'original')

    def test_arbitrary_path_is_rejected(self):
        other = self.root / 'canonical_cleaned.png'
        result = self.invoke(self.result(self.png()), target=other)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(other.exists())

    def test_ambiguous_multiple_images_are_rejected(self):
        a, b = self.result(self.png()), self.result(self.png())
        result = self.invoke({'content': [{'type': 'text', 'text': json.dumps(a)},
                                           {'type': 'text', 'text': json.dumps(b)}]})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.target.exists())


if __name__ == '__main__':
    unittest.main()
