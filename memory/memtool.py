#!/usr/bin/env python3
"""memtool.py — sim-forge 記憶庫的維護工具(純標準庫,系統 python3 就能跑,不需要 Isaac)。

    python3 memory/memtool.py find contactOffset 薄板        # 關鍵字找教訓(標題/標籤/觸發情境/內文)
    python3 memory/memtool.py find --domain surface          # 列出某領域全部教訓
    python3 memory/memtool.py show L0012                     # 印出一條教訓全文
    python3 memory/memtool.py new --domain rigid --title "…"  # 用模板開新教訓(自動配下一個編號)
    python3 memory/memtool.py build                          # 重產 INDEX.md(AI 看)與 HANDBOOK.md(人看)
    python3 memory/memtool.py check                          # 驗格式、編號、互相引用、產物是否過期;CI / commit 前跑

單一來源是 lessons/*.md。INDEX.md 與 HANDBOOK.md 都由這支產生,不要手改。
"""
import argparse, datetime, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LESSONS = os.path.join(HERE, "lessons")
TEMPLATE = os.path.join(HERE, "templates", "lesson.md")

# 領域詞彙表(受控詞彙)。新增領域改這裡,再跑 build。順序 = INDEX / HANDBOOK 的章節順序。
DOMAINS = [
    ("env",      "環境與啟動",       "Isaac 版本差異、python 直譯器、Kit 參數、ROS 2、背景程序"),
    ("usd",      "USD 編寫",         "defaultPrim、PhysicsScene 位置、scale、bbox、meta 檔"),
    ("render",   "渲染與影片",       "材質、貼圖、燈光、相機、錄影"),
    ("rigid",    "剛體/關節/碰撞",    "PhysicsScene 參數、contactOffset、kinematic、CCD、摺痕力矩"),
    ("surface",  "Surface deformable", "零厚度布 / 膜:rest shape、自碰撞、sleep、官方限制"),
    ("volume",   "Volume deformable",  "四面體薄板:rest shape、建板、反轉"),
    ("attach",   "Attachment 與夾持",  "錨點建立、放手、夾爪"),
    ("ui",       "UI 與互動",         "滑鼠拖曳、WebRTC、Script Editor"),
    ("measure",  "量測與驗收",        "判讀方法、恆真陷阱、非決定性、證據標準"),
    ("pipeline", "模擬鏈與檔案",      "多段續跑、參數一致、批次衛生、文件同步"),
    ("geometry", "幾何與座標",        "方位、置中、尺寸推導、紙箱幾何"),
    ("workflow", "Agent 協作",        "多 agent 並行修改、共享環境、證據與結論"),
]
DOMAIN_KEYS = [d[0] for d in DOMAINS]
SEVERITY = {"high": "高", "medium": "中", "low": "低"}
CONFIDENCE = ("measured", "observed", "inferred")
STATUS = ("active", "superseded", "disputed")
REQUIRED = ("id", "title", "status", "severity", "confidence", "domains", "triggers", "versions", "evidence", "observed")
LISTS = ("domains", "tags", "triggers", "scope", "evidence", "related", "supersedes")
REQ_SECTIONS = ("人話", "現象", "根因", "做法", "證據")


# ------------------------------------------------------------------ 解析
def parse_front(text, path):
    """極簡 frontmatter 解析:`key: value`、`key: [a, b]`、或 `key:` 下接 `  - item`。不依賴 PyYAML。"""
    if not text.startswith("---\n"):
        raise ValueError("%s:開頭不是 '---' frontmatter" % path)
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("%s:frontmatter 沒有結尾 '---'" % path)
    meta, key = {}, None
    for ln in text[4:end].splitlines():
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        if ln.startswith("  - ") or ln.startswith("- "):
            if key is None or not isinstance(meta.get(key), list):
                raise ValueError("%s:清單項目前面沒有 key:%r" % (path, ln))
            meta[key].append(ln.split("- ", 1)[1].strip())
            continue
        if ":" not in ln:
            raise ValueError("%s:看不懂這行:%r" % (path, ln))
        key, val = ln.split(":", 1)
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            meta[key] = [v.strip() for v in val[1:-1].split(",") if v.strip()]
        elif val == "" and key in LISTS:
            meta[key] = []
        else:
            meta[key] = val
    for k in LISTS:
        v = meta.get(k)
        if v is None:
            meta[k] = []
        elif isinstance(v, str):
            meta[k] = [v] if v else []
    return meta, text[end + 5:]


def sections(body):
    """回傳 {段名: 內容},段名取 `## ` 後到第一個空白或括號前。"""
    out, cur = {}, None
    for ln in body.splitlines():
        m = re.match(r"^## +(.+?)\s*$", ln)
        if m:
            cur = re.split(r"[ (（]", m.group(1))[0]
            out[cur] = []
        elif cur:
            out[cur].append(ln)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def load():
    items = []
    for fn in sorted(os.listdir(LESSONS)):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(LESSONS, fn)
        text = open(p, encoding="utf-8").read()
        meta, body = parse_front(text, fn)
        meta["_file"] = fn
        meta["_body"] = body
        meta["_sec"] = sections(body)
        items.append(meta)
    return items


def human(item):
    """抽「人話」段的 問題 / 做法。"""
    s = item["_sec"].get("人話", "")
    q = re.search(r"\*\*問題\*\*[::]\s*(.+?)(?=\n\*\*做法\*\*|\Z)", s, re.S)
    a = re.search(r"\*\*做法\*\*[::]\s*(.+)", s, re.S)
    return (q.group(1).strip() if q else ""), (a.group(1).strip() if a else "")


# ------------------------------------------------------------------ 產生
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def _sorted(xs):
    return sorted(xs, key=lambda m: (SEV_ORDER.get(m.get("severity"), 9), m["id"]))


def build_index(items):
    act = [m for m in items if m.get("status") != "superseded"]
    old = [m for m in items if m.get("status") == "superseded"]
    L = ["# INDEX —— 教訓索引(AI 讀這份;由 `memtool.py build` 產生,不要手改)", "",
         "用法見 [AGENTS.md](AGENTS.md)。每行:`編號 [嚴重度|信心] 規則 — 想起:何時 (+次領域) →檔案`。",
         "每條只列在主領域;次領域的關聯看下面的交叉表。`superseded` 的放最後,**不要照做**。", "",
         "共 %d 條(有效 %d、已推翻 %d)。" % (len(items), len(act), len(old)), "",
         "## 領域交叉表(**粗體** = 嚴重度高)", "",
         "| key | 領域 | 涵蓋 | 主領域 | 也相關 |", "|---|---|---|---|---|"]
    fmt = lambda xs: " ".join(("**%s**" if m["severity"] == "high" else "%s") % m["id"] for m in xs) or "—"
    for k, zh, desc in DOMAINS:
        pri = _sorted([m for m in act if m["domains"][0] == k])
        sec = _sorted([m for m in act if k in m["domains"][1:]])
        L.append("| `%s` | [%s](#%s) | %s | %s | %s |" % (k, zh, k, desc, fmt(pri), fmt(sec)))
    L.append("")
    for k, zh, desc in DOMAINS:
        xs = _sorted([m for m in act if m["domains"][0] == k])
        if not xs:
            continue
        L += ['<a id="%s"></a>' % k, "## %s `%s`" % (zh, k), ""]
        for m in xs:
            flag = " ⚠disputed" if m.get("status") == "disputed" else ""
            more = " (+%s)" % ",".join(m["domains"][1:]) if m["domains"][1:] else ""
            L.append("- **%s** [%s|%s]%s %s — 想起:%s%s [→](lessons/%s)"
                     % (m["id"], SEVERITY.get(m["severity"], m["severity"]), m["confidence"], flag,
                        m["title"], ";".join(m["triggers"]), more, m["_file"]))
        L.append("")
    if old:
        L += ["## 已推翻 / 過時(不要照做;留著是因為舊程式註解或舊文件還這樣寫)", ""]
        for m in sorted(old, key=lambda m: m["id"]):
            L.append("- ~~**%s** %s~~ → 改看 **%s** · [%s](lessons/%s)"
                     % (m["id"], m["title"], m.get("superseded_by", "?"), m["_file"], m["_file"]))
        L.append("")
    return "\n".join(L)


def build_handbook(items):
    act = [m for m in items if m.get("status") != "superseded"]
    L = ["# 踩坑手冊(給人看)", "",
         "sim-forge 做模擬時踩過的坑,每條只講「碰到什麼問題」和「該怎麼做」。",
         "細節、數字、程式碼在每條後面的編號連結裡(那是給 AI 看的詳細版)。", "",
         "> 本檔由 `python3 memory/memtool.py build` 從 `lessons/` 自動產生,**不要手改**;要改內容請改對應的 lessons 檔。", "",
         "嚴重度:**高** = 結果是錯的或整段白跑;**中** = 浪費一段時間;**低** = 小麻煩。", "", "## 目錄", ""]
    for k, zh, _ in DOMAINS:
        n = sum(1 for m in act if m["domains"][0] == k)
        if n:
            L.append("- [%s](#%s)(%d 條)" % (zh, k, n))
    L.append("")
    for k, zh, desc in DOMAINS:
        xs = _sorted([m for m in act if m["domains"][0] == k])
        if not xs:
            continue
        L += ['<a id="%s"></a>' % k, "## %s" % zh, "", "_%s_" % desc, ""]
        for m in xs:
            q, a = human(m)
            L += ["### %s" % m["title"], "",
                  "`%s` · 嚴重度 **%s** · [詳細](lessons/%s)" % (m["id"], SEVERITY.get(m["severity"], "?"), m["_file"]), "",
                  "**問題**:" + q, "", "**做法**:" + a, ""]
    return "\n".join(L)


def outputs(items):
    return {"INDEX.md": build_index(items) + "\n", "HANDBOOK.md": build_handbook(items) + "\n"}


# ------------------------------------------------------------------ 指令
def cmd_build(a):
    items = load()
    errs = validate(items, check_outputs=False)
    if errs:
        print("\n".join(errs)); print("先修上面的錯誤再 build"); return 1
    for fn, txt in outputs(items).items():
        open(os.path.join(HERE, fn), "w", encoding="utf-8").write(txt)
        print("寫入 %s" % fn)
    return 0


def validate(items, check_outputs=True):
    errs, ids = [], {}
    for m in items:
        f = m["_file"]
        for k in REQUIRED:
            if not m.get(k):
                errs.append("%s:缺欄位 %s" % (f, k))
        i = m.get("id", "")
        if not re.fullmatch(r"L\d{4}", i):
            errs.append("%s:id 格式要是 L0000" % f)
        elif not f.startswith(i + "-"):
            errs.append("%s:檔名要以 %s- 開頭" % (f, i))
        if i in ids:
            errs.append("%s:id %s 跟 %s 重複" % (f, i, ids[i]))
        ids[i] = f
        if m.get("status") not in STATUS:
            errs.append("%s:status 只能是 %s" % (f, "/".join(STATUS)))
        if m.get("severity") not in SEVERITY:
            errs.append("%s:severity 只能是 %s" % (f, "/".join(SEVERITY)))
        if m.get("confidence") not in CONFIDENCE:
            errs.append("%s:confidence 只能是 %s" % (f, "/".join(CONFIDENCE)))
        for d in m["domains"]:
            if d not in DOMAIN_KEYS:
                errs.append("%s:未知領域 %s(可用:%s)" % (f, d, ", ".join(DOMAIN_KEYS)))
        if not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", m.get("observed", "")):
            errs.append("%s:observed 要是 YYYY-MM 或 YYYY-MM-DD" % f)
        for s in REQ_SECTIONS:
            if not m["_sec"].get(s):
                errs.append("%s:缺段落 ## %s" % (f, s))
        q, ans = human(m)
        if not q or not ans:
            errs.append("%s:## 人話 要有 **問題**: 與 **做法**: 兩行" % f)
        if m.get("status") == "superseded" and not m.get("superseded_by"):
            errs.append("%s:superseded 要填 superseded_by" % f)
    for m in items:
        for k in ("related", "supersedes"):
            for r in m[k]:
                if r not in ids:
                    errs.append("%s:%s 指到不存在的 %s" % (m["_file"], k, r))
        sb = m.get("superseded_by")
        if sb and sb not in ids:
            errs.append("%s:superseded_by 指到不存在的 %s" % (m["_file"], sb))
        for r in m["supersedes"]:
            tgt = next((x for x in items if x.get("id") == r), None)
            if tgt and tgt.get("superseded_by") != m.get("id"):
                errs.append("%s:supersedes %s,但 %s 的 superseded_by 不是 %s" % (m["_file"], r, r, m.get("id")))
    if check_outputs and not errs:
        for fn, txt in outputs(items).items():
            p = os.path.join(HERE, fn)
            if not os.path.exists(p) or open(p, encoding="utf-8").read() != txt:
                errs.append("%s 過期了:跑 python3 memory/memtool.py build" % fn)
    return errs


def cmd_check(a):
    items = load()
    errs = validate(items)
    if errs:
        print("\n".join("✗ " + e for e in errs)); print("FAIL(%d 個問題)" % len(errs)); return 1
    print("OK:%d 條教訓,INDEX.md / HANDBOOK.md 是最新的" % len(items)); return 0


def cmd_find(a):
    items = load()
    kws = [k.lower() for k in a.keywords]
    hits = []
    for m in items:
        if a.domain and a.domain not in m["domains"]:
            continue
        if m.get("status") == "superseded" and not a.all:
            continue
        head = " ".join([m["title"]] + m["tags"] + m["triggers"]).lower()
        hay = head + " " + m["_body"].lower()
        if all(k in hay for k in kws):
            score = sum(3 if k in head else 1 for k in kws) + (2 - SEV_ORDER.get(m["severity"], 2))
            hits.append((score, m))
    if not hits:
        print("找不到。試試更短的關鍵字、英文 API 名稱,或 --all 包含已推翻的。"); return 1
    for _, m in sorted(hits, key=lambda x: (-x[0], x[1]["id"])):
        print("%s [%s|%s|%s] %s\n    何時想起:%s\n    lessons/%s"
              % (m["id"], SEVERITY.get(m["severity"]), m["confidence"], m["status"], m["title"],
                 ";".join(m["triggers"]), m["_file"]))
    return 0


def cmd_show(a):
    for m in load():
        if m["id"] == a.id:
            print(open(os.path.join(LESSONS, m["_file"]), encoding="utf-8").read()); return 0
    print("沒有 %s" % a.id); return 1


def cmd_new(a):
    items = load()
    if a.domain not in DOMAIN_KEYS:
        print("未知領域 %s(可用:%s)" % (a.domain, ", ".join(DOMAIN_KEYS))); return 1
    nid = "L%04d" % (max([int(m["id"][1:]) for m in items] or [0]) + 1)
    slug = re.sub(r"[^a-z0-9]+", "-", (a.slug or "lesson").lower()).strip("-") or "lesson"
    p = os.path.join(LESSONS, "%s-%s.md" % (nid, slug))
    t = open(TEMPLATE, encoding="utf-8").read()
    t = (t.replace("L0000", nid).replace("<一句祈使句規則>", a.title)
          .replace("domains: [env]", "domains: [%s]" % a.domain)
          .replace("2026-01-01", datetime.date.today().isoformat()))
    open(p, "w", encoding="utf-8").write(t)
    print("建立 %s —— 填完後跑 python3 memory/memtool.py build && python3 memory/memtool.py check" % os.path.relpath(p))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    f = sub.add_parser("find"); f.add_argument("keywords", nargs="*"); f.add_argument("--domain", choices=DOMAIN_KEYS)
    f.add_argument("--all", action="store_true", help="包含已推翻的"); f.set_defaults(fn=cmd_find)
    s = sub.add_parser("show"); s.add_argument("id"); s.set_defaults(fn=cmd_show)
    n = sub.add_parser("new"); n.add_argument("--domain", required=True); n.add_argument("--title", required=True)
    n.add_argument("--slug", default="", help="英文短名,當檔名用"); n.set_defaults(fn=cmd_new)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
