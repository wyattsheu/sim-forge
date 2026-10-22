"""Execute the actual credential forwarder in isolated JS tool sessions."""
from pathlib import Path
import shutil
import subprocess
import inspect
import sys
import unittest

SOURCE = Path(__file__).resolve().parents[3] / "tools/diaggen_support/diagnostic_credentials.js"
HARNESS = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
const methods = ['attach_diagnostic_run', 'compute_part_grounding_context', 'create_genesis_live_session',
  'inspect_genesis_runtime_logs', 'record_diagnostic_evidence', 'close_genesis_live_session',
  'submit_diagnostic_recommendation', 'halt_diagnostics', 'revise_diagnostic_probe_target'];
function setup(options = {}) {
  const memory = new Map(); const calls = []; const displayed=[];
  const auth = {run_root:'/native/outputs/run', agent_invocation_id:'fresh-id',
    owner_lease_token:'opaque-original-token-000000000000000000000', attachment_id:'opaque-attachment', owner_lease_timeout_s:3900};
  const tools = {}; const ALL_TOOLS = methods.map(name => ({name:'mcp__hag4r_genesis_diagnostics__'+name}));
  for (const name of methods) tools['mcp__hag4r_genesis_diagnostics__'+name] = async args => {
    calls.push({name, args});
    if (name === 'attach_diagnostic_run') {
      if (options.attachError) return {isError:true,result:[{type:'text',text:'actual native attach rejection'}]};
      const result = {...auth, ...(options.badIdentity ? {agent_invocation_id:'wrong-id'} : {})};
      if (options.duplicateCredentials) return {content:[{type:'text', text:JSON.stringify(result)},
        {type:'text', text:JSON.stringify({...result, owner_lease_token:'different'})}]};
      return options.structured ? {structuredContent:result, content:[{type:'text',text:JSON.stringify(result)}]} :
        {content:[{type:'text',text:JSON.stringify(result)}]};
    }
    assert.equal(args.owner_lease_token, auth.owner_lease_token);
    assert.equal(args.run_root, auth.run_root);
    assert.equal(args.agent_invocation_id, auth.agent_invocation_id);
    if (options.transportError) return {isError:true, content:[{type:'text',text:'Error: diagnostic owner lease token does not match'}]};
    if (options.schemaError) return {isError:true,content:[{type:'text',text:'Error: expected a well-formed region'}]};
    if (name === 'create_genesis_live_session') return {content:[{type:'text',text:JSON.stringify({live_session_handle:'exact-live-handle'})}]};
    if (name === 'inspect_genesis_runtime_logs') assert.equal(args.live_session_handle,'exact-live-handle');
    if (name === 'revise_diagnostic_probe_target') {
      const content=[{type:'text',text:JSON.stringify({status:'success',compile_id:'actual-native-compile-02',
        triple_view_evidence_id:'actual-native-preview-02',triptych_png_path:'/native/outputs/run/actual.png'})},
        {type:'image',mimeType:'image/png',data:'unchanged-image-bytes'}];
      return options.arrayReply ? content : {isError:false,result:content};
    }
    return {content:[{type:'text',text:JSON.stringify({status:'success'})}]};
  };
  const context = vm.createContext({tools, ALL_TOOLS, store:(k,v)=>memory.set(k,structuredClone(v)), load:k=>memory.get(k),
    text:value=>displayed.push({type:'text',value}),image:value=>displayed.push({type:'image',value})});
  return {calls, memory, auth, context, displayed, client:()=>vm.runInContext(source, context)};
}
(async () => {
CASE
})().catch(error => { console.error(error); process.exitCode=1; });
'''


class CredentialForwarderTests(unittest.TestCase):
    def test_native_authenticated_log_signature_requires_forwarded_credentials(self):
        sys.path.insert(0, str(SOURCE.parent.parent / "diaggen"))
        from hag4r.agentic.diagnostic_mcp_server import _authenticated_diagnostic_signature
        from hag4r.agentic.runtime_tools import diagnostics
        signature = _authenticated_diagnostic_signature(diagnostics.inspect_genesis_runtime_logs)
        for name in ("run_root", "agent_invocation_id", "owner_lease_token", "live_session_handle"):
            self.assertEqual(signature.parameters[name].default, inspect.Parameter.empty)
            self.assertEqual(signature.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)

    def run_js(self, case):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required to test the real JS source")
        result = subprocess.run([node, "-e", HARNESS.replace("CASE", case), str(SOURCE)],
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fifty_requests_reuse_exact_token_across_fresh_exec_context_evaluations(self):
        self.run_js("""const s=setup(); const result=await s.client().attach('/native/outputs/run','fresh-id');
          assert(!JSON.stringify(result).includes(s.auth.owner_lease_token));
          for(let i=0;i<50;i++) await s.client().call('compute_part_grounding_context',{});
          assert.equal(s.calls.length,51);""")

    def test_transcribed_credentials_rejected_before_any_native_request(self):
        self.run_js("""const s=setup(); await s.client().attach('/native/outputs/run','fresh-id');
          for(const key of ['run_root','agent_invocation_id','owner_lease_token','attachment_id','live_session_handle'])
            await assert.rejects(s.client().call('record_diagnostic_evidence',{[key]:'one-character-typo'}),/Do not supply/);
          assert.equal(s.calls.length,1);""")

    def test_separate_child_cannot_load_another_child_credentials(self):
        self.run_js("""const s=setup(); await s.client().attach('/native/outputs/run','fresh-id');
          const fresh=setup(); await assert.rejects(fresh.client().call('compute_part_grounding_context',{}),/No usable/);
          assert.equal(fresh.calls.length,0);""")

    def test_evidence_payload_is_forwarded_unchanged_after_local_identity_argument_correction(self):
        self.run_js("""const s=setup(); await s.client().attach('/native/outputs/run','fresh-id');
          const evidence={schema_version:'hag4r-genesis-vlm-reflection-v2',phase:'post_probe',
            episode_id:'episode_0001',next_action:'close_genesis_live_session',
            artifact_refs:[{kind:'tool_result',ref:'tool_result:10',note:'Actual observed result'}]};
          await assert.rejects(s.client().call('record_diagnostic_evidence',{
            run_root:s.auth.run_root,agent_invocation_id:s.auth.agent_invocation_id,evidence}),
            /fields: run_root, agent_invocation_id.*No native request was sent/);
          assert.equal(s.calls.length,1);
          await s.client().call('record_diagnostic_evidence',{evidence});
          assert.equal(s.calls.length,2);assert.deepEqual(s.calls[1].args.evidence,evidence);
          assert.equal(s.calls[1].args.owner_lease_token,s.auth.owner_lease_token);
          assert(!Object.hasOwn(s.calls[1].args,'live_session_handle'));""")

    def test_live_handle_is_retained_without_transcription(self):
        self.run_js("""const s=setup(); await s.client().attach('/native/outputs/run','fresh-id');
          await assert.rejects(s.client().call('inspect_genesis_runtime_logs',{}),/no retained/);
          await s.client().call('create_genesis_live_session',{episode_id:'episode_0001'});
          await s.client().call('inspect_genesis_runtime_logs',{stream:'both'});
          assert.equal(s.calls.length,3);""")

    def test_successful_terminal_disallows_further_calls(self):
        self.run_js("""const s=setup(); await s.client().attach('/native/outputs/run','fresh-id');
          await s.client().call('halt_diagnostics',{reason:'preserve actual failure'});
          await assert.rejects(s.client().call('compute_part_grounding_context',{}),/No usable/);
          assert.equal(s.calls.length,2);""")

    def test_authentication_error_stops_without_retrying(self):
        self.run_js("""const s=setup({transportError:true}); await s.client().attach('/native/outputs/run','fresh-id');
          const r=await s.client().call('compute_part_grounding_context',{}); assert(r.isError);
          await assert.rejects(s.client().call('compute_part_grounding_context',{}),/No usable/);
          assert.equal(s.calls.length,2);""")

    def test_schema_failure_preserves_response_and_does_not_invent_terminal(self):
        self.run_js("""const s=setup({schemaError:true}); await s.client().attach('/native/outputs/run','fresh-id');
          const r=await s.client().call('record_diagnostic_evidence',{evidence:{}});
          assert(r.isError); assert.equal(s.calls.length,2);""")

    def test_second_attach_is_blocked(self):
        self.run_js("""const s=setup(); await s.client().attach('/native/outputs/run','fresh-id');
          await assert.rejects(s.client().attach('/native/outputs/run','new-id'),/exactly once/);
          assert.equal(s.calls.length,1);""")

    def test_wrong_identity_response_is_rejected_and_not_retried(self):
        self.run_js("""const s=setup({badIdentity:true});
          await assert.rejects(s.client().attach('/native/outputs/run','fresh-id'),/identity/);
          await assert.rejects(s.client().call('compute_part_grounding_context',{}),/No usable/);
          assert.equal(s.calls.length,1);""")

    def test_structured_and_text_duplicate_of_same_credential_is_accepted(self):
        self.run_js("""const s=setup({structured:true}); await s.client().attach('/native/outputs/run','fresh-id');
          await s.client().call('compute_part_grounding_context',{}); assert.equal(s.calls.length,2);""")

    def test_conflicting_credentials_are_rejected(self):
        self.run_js("""const s=setup({duplicateCredentials:true});
          await assert.rejects(s.client().attach('/native/outputs/run','fresh-id'),/ambiguous/);
          assert.equal(s.calls.length,1);""")

    def test_unknown_tool_is_not_guessed_or_called(self):
        self.run_js("""const s=setup(); await s.client().attach('/native/outputs/run','fresh-id');
          await assert.rejects(s.client().call('invented_diagnostic_tool',{}),/Exactly one/);
          assert.equal(s.calls.length,1);""")

    def test_result_envelope_exposes_original_text_and_images_as_content(self):
        self.run_js("""const s=setup(); await s.client().attach('/native/outputs/run','fresh-id');
          const r=await s.client().call('revise_diagnostic_probe_target',{compile_id:'old',edit:{}});
          assert.equal(r.content[0],r.result[0]); assert.equal(r.content[1].data,'unchanged-image-bytes');
          assert.equal(s.calls.length,2);""")

    def test_native_identifiers_remain_retrievable_without_another_runtime_call(self):
        self.run_js("""const s=setup(); await s.client().attach('/native/outputs/run','fresh-id');
          await s.client().call('revise_diagnostic_probe_target',{compile_id:'old',edit:{}});
          await s.client().call('compute_part_grounding_context',{});
          const r=s.client().lastMetadata('revise_diagnostic_probe_target');
          const actual=r.records.find(item=>item.compile_id==='actual-native-compile-02');
          assert.equal(actual.triple_view_evidence_id,'actual-native-preview-02');
          assert.equal(actual.triptych_png_path,'/native/outputs/run/actual.png');
          assert.equal(s.calls.length,3);""")

    def test_direct_content_array_is_normalized_and_missing_metadata_fails_closed(self):
        self.run_js("""const s=setup({arrayReply:true}); await s.client().attach('/native/outputs/run','fresh-id');
          assert.throws(()=>s.client().lastMetadata('not_called'),/No retained/);
          const r=await s.client().call('revise_diagnostic_probe_target',{compile_id:'old',edit:{}});
          assert.equal(r.content.length,2);assert.equal(s.calls.length,2);""")

    def test_show_forwards_native_text_and_image_without_extra_runtime_request(self):
        self.run_js("""const s=setup(); await s.client().attach('/native/outputs/run','fresh-id');
          const r=await s.client().call('revise_diagnostic_probe_target',{compile_id:'old',edit:{}});
          s.client().show(r); assert.equal(s.displayed.length,2);
          assert.equal(JSON.parse(s.displayed[0].value).compile_id,'actual-native-compile-02');
          assert.equal(s.displayed[1].value.data,'unchanged-image-bytes');assert.equal(s.calls.length,2);""")

    def test_native_attach_error_cannot_be_ignored_as_success_and_retains_real_reason(self):
        self.run_js("""const s=setup({attachError:true}); let falselyClaimed=false;
          await assert.rejects((async()=>{await s.client().attach('/native/outputs/run','fresh-id'); falselyClaimed=true;})(),
            /Native diagnostic attach rejected: actual native attach rejection/);
          assert.equal(falselyClaimed,false);assert.equal(s.calls.length,1);
          await assert.rejects(s.client().call('compute_part_grounding_context',{}),/No usable/);""")


if __name__ == "__main__":
    unittest.main()
