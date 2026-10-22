// Evaluate this expression inside functions.exec. It forwards one native MCP
// call at a time; it does not plan, retry, advance stages, or decide outcomes.
// Private store/load belong to the owning child's tool session. Never export
// this store to a parent, file, command line, or another diagnostic invocation.
(() => {
  const bindingKey = "diaggen_diagnostic_credential_binding_v1";
  const metadataKey = "diaggen_native_metadata_v1";
  const terminalTools = new Set(["submit_diagnostic_recommendation", "halt_diagnostics"]);
  const handleTools = new Set([
    "bind_genesis_live_handlers", "get_genesis_live_session_status",
    "close_genesis_live_session", "inspect_genesis_runtime_logs",
    "simulation_reset", "simulate", "query_live_geometry_context",
  ]);
  function objects(value, depth = 0, found = []) {
    if (depth > 12) throw new Error("MCP response nesting exceeds safe limit");
    if (typeof value === "string") {
      try { objects(JSON.parse(value), depth + 1, found); } catch (error) {
        if (!(error instanceof SyntaxError)) throw error;
      }
    } else if (Array.isArray(value)) {
      for (const item of value) objects(item, depth + 1, found);
    } else if (value && typeof value === "object") {
      found.push(value);
      for (const [key, item] of Object.entries(value)) {
        if (["content", "result", "structuredContent", "text"].includes(key)) objects(item, depth + 1, found);
      }
    }
    return found;
  }
  function endpoint(name) {
    const matches = ALL_TOOLS.filter(item =>
      item.name.includes("hag4r_genesis_diagnostics") && item.name.endsWith("__" + name));
    if (matches.length !== 1 || typeof tools[matches[0].name] !== "function") {
      throw new Error("Exactly one native diagnostic MCP endpoint is required: " + name);
    }
    return tools[matches[0].name];
  }
  function normalize(result) {
    const blocks = Array.isArray(result) ? result :
      Array.isArray(result?.content) ? result.content :
      Array.isArray(result?.result) ? result.result : null;
    if (!blocks || !blocks.every(item => item && typeof item.type === "string")) return result;
    return Array.isArray(result) ? {content: blocks} : {...result, content: blocks};
  }
  function retainMetadata(name, payloads) {
    const keys = ["compile_id", "triple_view_evidence_id", "target_id", "anchor_id", "episode_id",
                  "trial_id", "triptych_png_path", "preview_manifest_path", "next_action", "status",
                  "selected_part_id", "part_name", "part_semantics"];
    const records = payloads.map(item => Object.fromEntries(keys.filter(key =>
      ["string", "number", "boolean"].includes(typeof item[key])).map(key => [key, item[key]])))
      .filter(item => Object.keys(item).length);
    const value = {tool: name, records};
    store(metadataKey, value);
    store(metadataKey + ":" + name, value);
  }
  function getBinding() {
    const record = load(bindingKey);
    if (!record || record.closed || record.authInvalid) {
      throw new Error("No usable credentials in this child session; stop this invocation");
    }
    return record;
  }
  return {
    show(result) {
      const normalized = normalize(result);
      if (!Array.isArray(normalized?.content)) { text(normalized); return; }
      for (const item of normalized.content) {
        if (item.type === "image") image(item);
        else if (item.type === "text") text(item.text);
      }
    },
    lastMetadata(name) {
      const value = load(name ? metadataKey + ":" + name : metadataKey);
      if (!value) throw new Error("No retained native metadata for this child/tool; never guess identifiers");
      return value;
    },
    async attach(runRoot, invocationId) {
      if (load(bindingKey)) throw new Error("Attach is allowed exactly once per child session");
      if (typeof runRoot !== "string" || !runRoot.startsWith("/") ||
          typeof invocationId !== "string" || !invocationId.trim()) {
        throw new Error("Canonical run root and fresh invocation ID are required");
      }
      // Claim this child's one attach attempt before calling the server.
      store(bindingKey, {authInvalid: true});
      const result = await endpoint("attach_diagnostic_run")({run_root: runRoot, agent_invocation_id: invocationId});
      const payloads = objects(result);
      if (payloads.some(item => item.isError === true)) {
        const message = payloads.filter(item => typeof item.text === "string")
          .map(item => item.text).join("\n").slice(0, 2000);
        throw new Error("Native diagnostic attach rejected: " + (message || "native MCP error without message"));
      }
      const candidates = payloads.filter(item => typeof item.owner_lease_token === "string");
      const unique = new Map(candidates.map(item => [JSON.stringify(item), item]));
      if (unique.size !== 1) throw new Error("Attach response has missing or ambiguous credentials");
      const auth = [...unique.values()][0];
      if (auth.run_root !== runRoot || auth.agent_invocation_id !== invocationId ||
          !auth.owner_lease_token || typeof auth.attachment_id !== "string" || !auth.attachment_id) {
        throw new Error("Attach credential identity does not match this invocation");
      }
      store(bindingKey, {
        auth: {run_root: auth.run_root, agent_invocation_id: auth.agent_invocation_id,
               owner_lease_token: auth.owner_lease_token},
        attachmentId: auth.attachment_id, handle: null, closed: false, authInvalid: false,
      });
      // The model never needs to transcribe the opaque token.
      return {status: "attached", run_root: auth.run_root, agent_invocation_id: auth.agent_invocation_id,
              attachment_id: auth.attachment_id, owner_lease_timeout_s: auth.owner_lease_timeout_s};
    },
    async call(name, args = {}) {
      if (name === "attach_diagnostic_run") throw new Error("Use the one-time attach method");
      if (!args || typeof args !== "object" || Array.isArray(args)) throw new Error("Arguments must be one object");
      if (["run_root", "agent_invocation_id", "owner_lease_token", "attachment_id", "live_session_handle"]
          .some(key => Object.prototype.hasOwnProperty.call(args, key))) {
        throw new Error("Do not supply or transcribe authentication/session fields");
      }
      const record = getBinding();
      const request = {...args, ...record.auth};
      if (handleTools.has(name)) {
        if (typeof record.handle !== "string" || !record.handle) throw new Error("This child has no retained live session handle");
        request.live_session_handle = record.handle;
      }
      const result = await endpoint(name)(request);
      const payloads = objects(result);
      retainMetadata(name, payloads);
      const failed = payloads.some(item => item.isError === true);
      if (failed) {
        const messages = payloads.filter(item => typeof item.text === "string").map(item => item.text).join("\n");
        if (/owner lease token does not match|no diagnostic attachment|lease has expired|invocation does not match|attachment is stale|superseded|credential/i.test(messages)) {
          record.authInvalid = true;
          store(bindingKey, record);
        }
        return normalize(result);
      }
      if (name === "create_genesis_live_session") {
        const handles = [...new Set(payloads.map(item => item.live_session_handle).filter(item => typeof item === "string" && item))];
        if (handles.length !== 1) throw new Error("Create response has missing or ambiguous live handle");
        record.handle = handles[0];
      }
      if (terminalTools.has(name)) record.closed = true;
      store(bindingKey, record);
      return normalize(result);
    },
  };
})()
