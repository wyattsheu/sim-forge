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

    def invoke(self, payload, *, target=None, simulate_bwrap=False,
               reject_review=False, default_error=None):
        if isinstance(payload, dict):
            marker = payload.get('image_url', '')
            if not marker and payload.get('content'):
                marker = payload['content'][0].get('data', '')
        else:
            marker = ''
        request = {'result': payload, 'root': str(self.root),
                   'target': str(target or self.target), 'python': sys.executable,
                   'helper': str(HELPER), 'simulate_bwrap': simulate_bwrap,
                   'reject_review': reject_review, 'default_error': default_error,
                   'payload_marker': marker[:256]}
        script = """
const fs = require('node:fs');
const cp = require('node:child_process');
const crypto = require('node:crypto');
const req = JSON.parse(fs.readFileSync(0, 'utf8'));
const sessions = new Map();
const calls = [];
let nextSession = 1;
global.tools = {
  exec_command: async (opts) => {
    const elevated = opts.sandbox_permissions === 'require_escalated';
    calls.push({elevated, command_sha256:crypto.createHash('sha256').update(opts.cmd).digest('hex'),
      command_length:opts.cmd.length, command_contains_payload:opts.cmd.includes(req.payload_marker)});
    if (req.simulate_bwrap && calls.length === 1 && !elevated)
      return {exit_code:1,output:'bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted'};
    if (elevated && req.reject_review) return {isError:true,output:'automatic review rejected'};
    if (!elevated && req.default_error) return {exit_code:1,output:req.default_error};
    const child = cp.spawn('/bin/bash',['-c',opts.cmd],{stdio:['pipe','pipe','pipe']});
    const id = nextSession++;
    const state = {child,output:'',done:false,exit_code:null};
    state.closed = new Promise(resolve => child.on('close',(code) => {
      state.done = true; state.exit_code = code; resolve();
    }));
    child.stdout.on('data',chunk => state.output += chunk.toString());
    child.stderr.on('data',chunk => state.output += chunk.toString());
    child.stdin.on('error',() => {});
    sessions.set(id,state);
    return await new Promise((resolve,reject) => {
      child.once('spawn',() => resolve({session_id:id,output:''}));
      child.once('error',reject);
    });
  },
  write_stdin: async ({session_id,chars='',yield_time_ms=250}) => {
    const state = sessions.get(session_id);
    if (!state) return {exit_code:1,output:'stdin session missing'};
    if (chars) await new Promise((resolve,reject) =>
      state.child.stdin.write(chars,error => error ? reject(error) : resolve()));
    await Promise.race([state.closed,new Promise(resolve => setTimeout(resolve,Math.max(10,yield_time_ms)))]);
    const output = state.output; state.output = '';
    if (state.done) { sessions.delete(session_id); return {exit_code:state.exit_code,output}; }
    return {session_id,output};
  }
};
(async () => {
  const save = eval(fs.readFileSync(req.helper,'utf8'));
  try { console.log(JSON.stringify({saved:await save(req.result,req.root,req.target,req.python),calls})); }
  catch (e) { console.error(JSON.stringify({error:e.message,calls})); process.exitCode=1; }
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
        result = self.invoke(self.result(data), simulate_bwrap=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), data)
        response = json.loads(result.stdout)
        self.assertEqual(response['saved']['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(response['saved']['bytes'], len(data))
        self.assertEqual(len(response['calls']), 2)
        self.assertEqual([call['elevated'] for call in response['calls']], [False, True])
        self.assertEqual(response['calls'][0]['command_sha256'], response['calls'][1]['command_sha256'])
        self.assertTrue(all(not call['command_contains_payload'] for call in response['calls']))
        self.assertLess(max(call['command_length'] for call in response['calls']), 8192)
        self.assertLess(len(result.stdout), 1000)
        self.assertFalse((ROOT / 'SHOULD_NOT_EXIST').exists())

    def test_review_rejection_does_not_retry_or_write_any_bytes(self):
        data = self.png()
        result = self.invoke(self.result(data), simulate_bwrap=True, reject_review=True)
        self.assertNotEqual(result.returncode, 0)
        response = json.loads(result.stderr)
        self.assertEqual(len(response['calls']), 2)
        self.assertEqual([call['elevated'] for call in response['calls']], [False, True])
        self.assertEqual(response['calls'][0]['command_sha256'], response['calls'][1]['command_sha256'])
        self.assertFalse(self.target.exists())
        self.assertFalse(self.target.with_name(self.target.name + '.imagegen.part').exists())

    def test_non_bwrap_failure_is_not_escalated_or_retried(self):
        result = self.invoke(self.result(self.png()), default_error='python writer unavailable')
        self.assertNotEqual(result.returncode, 0)
        response = json.loads(result.stderr)
        self.assertEqual(len(response['calls']), 1)
        self.assertFalse(response['calls'][0]['elevated'])
        self.assertFalse(self.target.exists())

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
