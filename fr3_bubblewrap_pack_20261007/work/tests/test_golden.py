#!/usr/bin/env python3
"""test_golden.py — 測試集自己的測試:好的 run 要 PASS/WARN,已知壞的 run 必須被預期那一項抓到 FAIL
(bad 可另列 expect_warn:那幾項必須是 WARN)。surface / vol 都在同一份 golden.json,kind 自動判斷。

    python3 tests/test_golden.py          # exit 0 = 全部符合預期;1 = 有好案例被誤判或壞案例漏抓

抓不到已知壞案例 = 測試集無效。漏抓就如實列出,不要調門檻去湊。
"""
import json
import os
import sys

T = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, T)
import run_checks as RC  # noqa: E402

G = json.load(open(os.path.join(T, "golden", "golden.json"), encoding="utf-8"))
ok_all, lines = True, []
for name, spec in G["good"].items():
    R, stage = RC.run(os.path.join(T, "golden", name))
    overall, c = RC.summary(R)
    fails = [i["key"] for i in R.items if i["status"] == "FAIL"]
    good = overall in ("PASS", "WARN")
    ok_all &= good
    lines.append("%-5s good %-22s stage %-8s 整體 %-4s (PASS %d WARN %d FAIL %d SKIP %d)%s"
                 % ("OK" if good else "MISS", name, stage, overall, c["PASS"], c["WARN"], c["FAIL"], c["SKIP"],
                    "  ← 誤判 FAIL: %s" % ",".join(fails) if fails else ""))
for name, spec in G["bad"].items():
    R, stage = RC.run(os.path.join(T, "golden", name))
    overall, c = RC.summary(R)
    st = {i["key"]: i["status"] for i in R.items}
    fails = [k for k, v in st.items() if v == "FAIL"]
    warns = [k for k, v in st.items() if v == "WARN"]
    ef, ew = spec.get("expect_fail", []), spec.get("expect_warn", [])
    missed = [k for k in ef if st.get(k) != "FAIL"] + [k for k in ew if st.get(k) != "WARN"]
    good = (overall == "FAIL" if ef else overall in ("WARN", "FAIL")) and not missed
    ok_all &= good
    msg = "抓到 FAIL: %s" % (",".join(fails) or "無")
    if ew:
        msg += " / WARN: %s" % (",".join(warns) or "無")
    if missed:
        msg += "  ← 漏抓預期項 %s(實際 %s)" % (",".join(missed), ",".join("%s=%s" % (k, st.get(k, "無")) for k in missed))
    lines.append("%-5s bad  %-22s stage %-8s 整體 %-4s %s  [%s]" % ("OK" if good else "MISS", name, stage, overall, msg,
                                                                    spec["why"]))
print("\n".join(lines))
n_ok = sum(l.startswith("OK") for l in lines)
print("\n總結:%d / %d 符合預期%s" % (n_ok, len(lines), "" if ok_all else ";有誤判或漏抓,見 MISS 行"))
sys.exit(0 if ok_all else 1)
