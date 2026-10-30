# -*- coding: utf-8 -*-
import json, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image

d = Path(r"D:\Python\item\WindowPet\Window_Pet_Generator\photo_cartoon_instance\calib_seed777")
parts_dir = d / "parts"
names = ["head","body","arm_l","arm_r","leg_l","leg_r","eye_l","eye_r","mouth"]

print("=== 9 部件输出检查 ===")
all_ok = True
for n in names:
    p = parts_dir / f"{n}.png"
    if not p.exists():
        print(f"  {n:7s} [缺失]"); all_ok = False; continue
    a = np.asarray(Image.open(p).convert("RGBA"))[..., 3]
    opaque = int((a > 16).sum())
    bbox = Image.fromarray(a).getbbox()
    ok = opaque > 0
    if not ok: all_ok = False
    print(f"  {n:7s} {'OK' if ok else '空'}  不透明像素={opaque:6d}  bbox={bbox}")

print()
print("=== character.json 枢轴检查 ===")
doc = json.loads((d / "character.json").read_text(encoding="utf-8"))
piv = {n: doc["rig"]["parts"][n]["pivot"] for n in names}
for n in names:
    print(f"  {n:7s} pivot = {piv[n]}")
print("  id =", doc.get("id"), "| contract_version =", doc.get("contract_version"))

print()
print("=== 契约校验 ===")
r = subprocess.run([sys.executable, "tools/validate.py", "character", str(d), "--actions-dir", "assets/actions"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print("退出码:", r.returncode, "->", "PASS" if r.returncode == 0 else "FAIL")
if r.stdout.strip(): print("  stdout:", r.stdout.strip()[:900])
if r.stderr.strip(): print("  stderr:", r.stderr.strip()[:900])

# 合成预览
order = ["leg_l","leg_r","arm_l","arm_r","body","head","eye_l","eye_r","mouth"]
checker = np.zeros((512,512,3), np.uint8)
for y in range(512):
    for x in range(512):
        checker[y,x] = 52 if ((x//24+y//24)%2==0) else 36
comp = checker.astype(np.float32)
for n in order:
    a = np.asarray(Image.open(parts_dir/f"{n}.png").convert("RGBA"))
    al = a[...,3:4].astype(np.float32)/255.0
    comp = a[...,:3].astype(np.float32)*al + comp*(1-al)
Image.fromarray(np.clip(comp,0,255).astype(np.uint8),"RGB").save(d/"verify_preview.png")
print()
print("合成预览已保存:", d/"verify_preview.png")
print("9部件全部输出:", "是" if all_ok else "否(有缺失)")
