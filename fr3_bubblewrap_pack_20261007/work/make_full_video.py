#!/usr/bin/env python3
"""make_full_video.py — 把四段接成一支完整影片,每段加標題卡。

完整鏈路(軟版 thick 6 / young 2e4 / bend 4 / 分層 8):
  1 攤平 → 折 +y / -y
  2 折 +x / -x(第二段模擬,因為跑到一半沒辦法鬆手)
  3 六面剛性板壓實成方塊
  4 置中放進 270x230x130 紙箱 → 關下層蓋 → 關上層蓋
"""
import numpy as np, imageio.v3 as iio, sys, os
from PIL import Image, ImageDraw, ImageFont
try: F = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 34)
except Exception:
    try: F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
    except Exception: F = ImageFont.load_default()
try: F2 = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 22)
except Exception: F2 = F

SEGS = [("seg_m1c.mp4", "1 / 4   攤平 → 折 +y → 折 −y", "整條邊一起拉,兩段等距旋轉,布不被拉伸"),
        ("seg_m2.mp4",  "2 / 4   折 +x → 折 −x",        "第二段模擬:只留杯子上方壓住,其餘全部放力"),
        ("seg_p6.mp4",  "3 / 4   六面剛性板壓實",        "只壓頂面布會攤到 284x270;六面圍住壓成 251x209x131,放開不回彈"),
        ("seg_p6box.mp4","4 / 4   置中入箱 → 關蓋",      "270x230x130 紙箱;逐頂點驗證:布 0、杯子 0 超出內腔")]

def card(text, sub, size, n=45):
    im = Image.new("RGB", size, (14, 16, 20)); d = ImageDraw.Draw(im)
    w, h = size
    d.text((60, h//2 - 50), text, fill=(240, 240, 240), font=F)
    d.text((60, h//2 + 6), sub, fill=(150, 185, 220), font=F2)
    return [np.array(im)]*n

out = []
size = None
for f, t, sub in SEGS:
    if not os.path.exists(f):
        print("缺 %s" % f); continue
    V = iio.imread(f)
    if size is None: size = (V.shape[2], V.shape[1])
    out += card(t, sub, size)
    out += [np.array(x) for x in V]
    print("%-16s %4d 格" % (f, len(V)))
iio.imwrite(sys.argv[1] if len(sys.argv) > 1 else "full.mp4", out, fps=30, codec="libx264", quality=8)
print("→ %s,共 %d 格 (%.1f 秒)" % (sys.argv[1] if len(sys.argv) > 1 else "full.mp4", len(out), len(out)/30))
