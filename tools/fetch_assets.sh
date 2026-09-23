#!/bin/bash
# 取得第三方資產(不進版控)。目前只有 NVIDIA Isaac 官方馬克杯。
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Props/Mugs"
DST="$HERE/../sims/wrapped_mug/assets"
mkdir -p "$DST/texture"

for m in A2 B1 C1 D1; do
  echo "SM_Mug_$m.usd"
  curl -sS -f -o "$DST/SM_Mug_$m.usd" "$BASE/SM_Mug_$m.usd"
  for k in Albedo Normal ORM; do
    curl -sS -f -o "$DST/texture/T_Mug_${m}_${k}.png" "$BASE/texture/T_Mug_${m}_${k}.png" \
      || rm -f "$DST/texture/T_Mug_${m}_${k}.png"
  done
done
echo "-> $DST"
du -sh "$DST"
