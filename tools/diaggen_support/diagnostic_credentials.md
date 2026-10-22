# Owning diagnostic child's credential transport

Read the official Genesis diagnostic skill first. This helper forwards one native
MCP call with the original credentials; it does not choose actions, retry, plan,
probe, synthesize, close or finalize automatically. Only the owning diagnostic
child uses it. Never give its private store or credentials to the parent.

In the child's first `functions.exec` call, load the exact repository file and
retain the source in this child's tool store. This filesystem read is not a
diagnostic runtime action. The first diagnostic runtime action remains attach:

```javascript
const loaded = await tools.exec_command({
  cmd: "cat /mnt/HDD4/wyattsheu/ITRI/sim-forge/tools/diaggen_support/diagnostic_credentials.js",
  max_output_tokens: 6000
});
if (loaded.exit_code !== 0) throw new Error("Cannot load the credential forwarder");
store("diaggen_credential_forwarder_source_v1", loaded.output);
const client = eval(loaded.output);
text(await client.attach("THE_CANONICAL_RUN_ROOT_FROM_PARENT", "THE_FRESH_INVOCATION_ID_FROM_PARENT"));
```

Replace only those two identity placeholders with the exact parent-supplied
values. Do not print the loaded source or raw attach response. Endpoint discovery
uses `ALL_TOOLS` and requires exactly one enabled native diagnostic endpoint.

For every later diagnostic action, reload the retained source from the same
child's private tool store and explicitly request exactly one native call:

```javascript
const source = load("diaggen_credential_forwarder_source_v1");
if (typeof source !== "string") throw new Error("Child tool store was lost; stop this invocation");
const client = eval(source);
const result = await client.call("compute_part_grounding_context", {});
client.show(result);
```

Replace the tool name and ordinary arguments according to the official skill and
the tool's real signature. Do not add `run_root`, `agent_invocation_id`,
`owner_lease_token`, `attachment_id`, or `live_session_handle` to `call` arguments;
the helper supplies the original values. A newly created live session handle is
retained from that native response. Plans, scene/model payloads, episode IDs,
probe intents, evidence and recommendations remain authored by this child.

Use `client.show(result)` to display the original text and images; do not replace
it with a custom parser or a fabricated status summary. The forwarder preserves native text/image blocks and makes either MCP `result`
or `content` envelopes available under `result.content`. Do not write a custom
partial parser that only understands one envelope or silently loses identifiers.
After each call it retains native metadata in this child's private store. If a
formatter hid a result, recover its actual identifiers locally, without another
runtime action:

```javascript
const client = eval(load("diaggen_credential_forwarder_source_v1"));
text(client.lastMetadata("revise_diagnostic_probe_target"));
```

Use exactly the returned compile/evidence identifiers. A successful probe target
revision already compiled and recorded a new preview. Inspect the returned
`triptych_png_path` with `tools.view_image` (a read-only file view); **do not call
`preview_diagnostic_probe_target` again for that compile**. The reflection gate
requires exactly one preview. Never infer IDs from naming patterns. If native
metadata is genuinely missing, read the current run ledger without mutation to
recover its recorded identifiers and unique current preview; do not fabricate
evidence or alter ledgers. A previous auto-review denial of unsupported IDs does
not authorize resubmitting guessed IDs by another route.

For live calls use a single `await client.call(...)` and display that native
result. Preserve the same explicit call order and media inspection as the
official skill. A helper call is not permission to skip evidence or take a
terminal shortcut. Never run periodic renewals or background work.

Native tool responses can contain attachment/session identifiers and paths.
They are expected private diagnostic context inside this child's tool session;
receiving or displaying such a native response here is not an authentication
failure and is not a reason to stop. Do not manually transcribe those fields
into new requests; the helper retains and forwards them. Keep them out of the
final report to the parent and out of public outputs. The attach lease token is
retained by the helper and is not printed by its successful attach response.

On an actual stale/expired/mismatched credential error, stop immediately. Do not attach
again, recover the token from logs, edit this helper, write credentials to disk,
invoke a raw MCP endpoint as a workaround, or ask the parent to take over. Report
the actual error and existing artifacts without credentials. After the one
successful terminal call, make no further runtime calls.
