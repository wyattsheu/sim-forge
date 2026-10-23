// Evaluate this expression inside functions.exec, where tools.exec_command exists.
// Preserve the built-in result in store() and call this before emitting metadata.
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
mode,root_arg,target_arg,data,offset_arg=sys.argv[1:]
root=Path(root_arg).resolve(strict=True)
state=json.loads((root/'state.json').read_text())
if Path(state['run_root']).resolve()!=root: raise ValueError('Run root mismatch')
target=Path(target_arg)
if not target.is_absolute(): raise ValueError('Candidate must be absolute')
allowed=[Path(state['paths'][k]) for k in ('image_cleanup_attempt_1_path','image_cleanup_attempt_2_path')]
if target not in allowed or not target.resolve().is_relative_to(root):
    raise ValueError('Not a native cleanup candidate path')
if target.is_symlink() or target.exists(): raise ValueError('Candidate already exists')
part=target.with_name(target.name+'.imagegen.part')
offset=int(offset_arg)
if mode=='init':
    target.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(part,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    os.close(fd)
elif mode=='append':
    chunk=base64.b64decode(data,validate=True)
    fd=os.open(part,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW)
    with os.fdopen(fd,'ab') as f:
        if os.fstat(f.fileno()).st_size!=offset: raise ValueError('Chunk offset mismatch')
        f.write(chunk)
elif mode=='commit':
    if part.is_symlink() or part.stat().st_size!=offset: raise ValueError('Incomplete PNG')
    with Image.open(part) as im:
        if im.format!='PNG': raise ValueError('Not PNG')
        size=im.size
        im.verify()
    digest=hashlib.sha256(part.read_bytes()).hexdigest()
    os.link(part,target)  # Atomic and refuses overwrite.
    part.unlink()
    print(json.dumps({'path':str(target),'bytes':offset,'sha256':digest,'size':size,'format':'PNG'}))
else: raise ValueError('Unknown operation')
`;
  async function call(mode, data, offset) {
    const response = await tools.exec_command({
      cmd: [python, "-I", "-c", script, mode, runRoot, candidatePath, data, offset].map(quote).join(" "),
      max_output_tokens: 400,
      yield_time_ms: 10000,
    });
    if (response.exit_code !== 0) throw new Error("PNG persistence failed: " + response.output);
    return response.output;
  }
  await call("init", "", 0);
  let offset = 0;
  // Bounded arguments avoid the OS per-argument limit for multi-megabyte images.
  for (let i = 0; i < payload.length; i += 98304) {
    const chunk = payload.slice(i, i + 98304);
    await call("append", chunk, offset);
    offset += chunk.length / 4 * 3 - (chunk.endsWith("==") ? 2 : chunk.endsWith("=") ? 1 : 0);
  }
  return JSON.parse(await call("commit", "", offset));
})
