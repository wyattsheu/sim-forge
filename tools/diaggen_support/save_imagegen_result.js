// Evaluate inside functions.exec. Keep image bytes out of shell arguments and
// stdout; the nested writer receives bounded stdin chunks and returns metadata.
(async function saveImagegenResult(result, runRoot, candidatePath, python) {
  const urls = [];
  function collect(value) {
    if (!value || typeof value !== "object") return;
    if (typeof value.image_url === "string") urls.push(value.image_url);
    if (value.type === "image" && value.mimeType === "image/png" && typeof value.data === "string") {
      urls.push("data:image/png;base64," + value.data);
    }
    for (const block of value.content || []) {
      if (block.type === "text" && typeof block.text === "string") {
        try { collect(JSON.parse(block.text)); } catch (_) { /* non-JSON metadata */ }
      } else collect(block);
    }
  }
  if (typeof result === "string") {
    if (result.startsWith("data:")) urls.push(result);
    else collect(JSON.parse(result));
  } else collect(result);
  const unique = [...new Set(urls)];
  if (unique.length !== 1 || !unique[0].startsWith("data:image/png;base64,")) {
    throw new Error("Expected exactly one complete built-in PNG image result");
  }
  const payload = unique[0].slice("data:image/png;base64,".length);
  if (!payload.startsWith("iVBORw0KGgo") || payload.length % 4 ||
      !/^[A-Za-z0-9+/]+={0,2}$/.test(payload) || payload.length > 48 * 1024 * 1024) {
    throw new Error("Invalid or oversized PNG base64 payload");
  }

  const quote = value => "'" + String(value).replaceAll("'", "'\\''") + "'";
  const script = `
import base64,hashlib,json,os,sys
from pathlib import Path
from PIL import Image
root=Path(sys.argv[1]).resolve(strict=True)
target=Path(sys.argv[2])
state=json.loads((root/'state.json').read_text())
if Path(state['run_root']).resolve()!=root: raise ValueError('Run root mismatch')
if not target.is_absolute(): raise ValueError('Candidate must be absolute')
allowed=[Path(state['paths'][k]) for k in ('image_cleanup_attempt_1_path','image_cleanup_attempt_2_path')]
if target not in allowed or not target.resolve().is_relative_to(root):
    raise ValueError('Not a native cleanup candidate path')
if target.is_symlink() or target.exists(): raise ValueError('Candidate already exists')
part=target.with_name(target.name+'.imagegen.part')
target.parent.mkdir(parents=True,exist_ok=True)
fd=os.open(part,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
written=0
with os.fdopen(fd,'wb') as stream:
    for line in sys.stdin.buffer:
        chunk=line.rstrip(b'\\r\\n')
        if chunk==b'END': break
        data=base64.b64decode(chunk,validate=True)
        written+=len(data)
        if written>36*1024*1024: raise ValueError('PNG payload exceeds the validated limit')
        stream.write(data)
    else: raise ValueError('PNG stream ended before its commit marker')
if part.is_symlink() or part.stat().st_size!=written: raise ValueError('Incomplete PNG')
with Image.open(part) as im:
    if im.format!='PNG': raise ValueError('Not PNG')
    size=im.size
    im.verify()
digest=hashlib.sha256(part.read_bytes()).hexdigest()
os.link(part,target)  # Atomic and refuses overwrite.
part.unlink()
print(json.dumps({'path':str(target),'bytes':written,'sha256':digest,'size':size,'format':'PNG'}))
`;
  const command = [python, "-I", "-c", script, runRoot, candidatePath].map(quote).join(" ");
  const bwrapFailure = "bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted";
  const commandOptions = elevated => ({
    cmd: command,
    tty: false,
    max_output_tokens: 300,
    yield_time_ms: 1000,
    ...(elevated ? {
      sandbox_permissions: "require_escalated",
      justification: "Run this exact local PNG validation and persistence command after the required sandbox namespace setup failed."
    } : {})
  });
  const failureText = value => typeof value === "string" ? value :
    String(value?.output || value?.message || value?.content?.map?.(block => block.text || "").join(" ") || "");
  const isBwrapFailure = value => failureText(value).includes(bwrapFailure);
  let escalatedAttempted = false;
  const runCommand = elevated => {
    if (elevated) escalatedAttempted = true;
    return tools.exec_command(commandOptions(elevated));
  };
  let response;
  try {
    response = await runCommand(false);
  } catch (error) {
    if (!isBwrapFailure(error)) throw error;
    response = await runCommand(true);
  }
  if (!escalatedAttempted && (response?.isError || (response?.exit_code !== undefined && response.exit_code !== 0)) &&
      isBwrapFailure(response)) {
    response = await runCommand(true);
  }
  if (!response || response.isError) {
    throw new Error("PNG persistence command was rejected or could not start: " + failureText(response));
  }
  if (response.exit_code !== undefined && response.exit_code !== 0) {
    throw new Error("PNG persistence failed: " + failureText(response));
  }
  if (!Number.isInteger(response.session_id)) {
    throw new Error("PNG persistence did not return a live stdin session");
  }

  let session = response.session_id;
  let output = response.output || "";
  const chunkSize = 256 * 1024; // Multiple of four for independently decodable base64 lines.
  for (let i = 0; i < payload.length; i += chunkSize) {
    const sent = await tools.write_stdin({
      session_id: session,
      chars: payload.slice(i, i + chunkSize) + "\n",
      max_output_tokens: 100,
      yield_time_ms: 250
    });
    if (sent.output) output += sent.output;
    if (sent.exit_code !== undefined) {
      throw new Error("PNG persistence writer exited before the commit marker: " + output.slice(-2000));
    }
    if (!Number.isInteger(sent.session_id)) throw new Error("PNG persistence stdin session disappeared");
    session = sent.session_id;
  }
  let finished = await tools.write_stdin({
    session_id: session, chars: "END\n", max_output_tokens: 300, yield_time_ms: 250
  });
  if (finished.output) output += finished.output;
  for (let poll = 0; finished.exit_code === undefined && poll < 120; poll++) {
    if (!Number.isInteger(finished.session_id)) throw new Error("PNG persistence writer did not finish cleanly");
    finished = await tools.write_stdin({
      session_id: finished.session_id, chars: "", max_output_tokens: 300, yield_time_ms: 1000
    });
    if (finished.output) output += finished.output;
  }
  if (finished.exit_code !== 0) throw new Error("PNG persistence failed: " + output.slice(-2000));
  const lines = output.trim().split(/\r?\n/).filter(Boolean);
  if (!lines.length) throw new Error("PNG persistence returned no validation metadata");
  return JSON.parse(lines[lines.length - 1]);
})
