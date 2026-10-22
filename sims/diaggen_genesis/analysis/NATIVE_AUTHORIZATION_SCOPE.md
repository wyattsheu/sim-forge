# Native authentication and stage terminal scope

This records the existing user-authorized DiagGen workflow and actual call path.
It does not override an approval denial, authorize unrelated processes, permit a
parent to take over a diagnostic session, or invent a diagnostic outcome.

## Diagnostic authentication

The official MCP wrapper's `_authenticated_diagnostic_signature` requires
`run_root`, `agent_invocation_id`, and `owner_lease_token`; live tools additionally
require the retained session selector. Native calls necessarily contain those
fields. Omitting the token would make the tool call invalid.

The owning child's forwarder follows this checked path:

1. `attach` calls the native server exactly once and stores its returned token
   without modification in the same child's private tool store.
2. `client.call(tool_name, ordinary_arguments)` rejects any caller-supplied
   authentication or session fields before issuing a native request.
3. The helper builds the wire request from the retained authentication object;
   it supplies the original live handle for the native tools that require it.
4. The parent never receives that store; tokens are kept out of final reports and
   public progress. The native server still authenticates every request.

The JS regression suite executes this real source: 50 successive calls use the
identical native-issued token, manually supplied fields are rejected, and stores
are isolated between test child contexts. Actual sloth run
`genesis_sloth_20261022_clean_diagnostics3` used this forwarder for two closed,
settled, qualifying episodes and a strict native accept, followed by full export.

For sauce run `genesis_sauce_keeper_20261022_clean_diagnostics1`, the log-read
review claimed the caller directly supplied the token. The captured invocation
instead used `client.call` and contained no literal `owner_lease_token` argument.
The expanded native request contains that required field because the authorized
forwarder injects it. This source/call-path distinction is evidence for reviewing
a future properly grounded call; the denied call was not executed or retried by
an indirect route. That old run has since been cleaned up by native shutdown.

## Non-diagnostic stage terminals

The pipeline skill's exhaustive parent restrictions explicitly apply to Genesis
diagnostics. A diagnostic parent cannot fabricate a `business_halt` or close a
failed child's session. The normal stage skills still own their documented
`halt_*_stage` tools when required inputs or outputs genuinely fail their checks.
For example, image cleanup halts if its bounded attempts yield no generated
candidate or required registration data cannot be established. This is a stage
failure record, not a fabricated Genesis diagnostic business verdict.

For two generated cleanup candidates that both semantically fail, the official
cleanup skill's bounded selection rule selects the better complete candidate
pair while retaining the actual failed checks. Selection does not authorize
rewriting a failed validation to pass or fabricating imagegen evidence.

Continue unaffected authorized work. If a real review still rejects a requested
action after checking provenance and scope, stop that action, preserve the reason,
and report the block rather than deleting state, guessing credentials/evidence,
or trying another execution route.
