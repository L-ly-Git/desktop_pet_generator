# -*- coding: utf-8 -*-
"""重启本机 ComfyUI，使其加载已修补的 See-through 插件代码。"""
import subprocess
import sys
import time

# 1) 找到 ComfyUI 的 python 进程并记录启动命令行
cmd = [
    "powershell", "-NoProfile", "-Command",
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "Where-Object { $_.CommandLine -like '*ComfyUI*' -or $_.ExecutablePath -like '*ComfyUI*' } | "
    "Select-Object -ExpandProperty CommandLine"
]
out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)
lines = [l.strip() for l in out.stdout.splitlines() if l.strip()]
print("ComfyUI processes found:", len(lines))
for l in lines:
    print("  CMD:", l[:200])

# 2) 结束这些进程
kill = [
    "powershell", "-NoProfile", "-Command",
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "Where-Object { $_.CommandLine -like '*ComfyUI*' -or $_.ExecutablePath -like '*ComfyUI*' } | "
    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
]
subprocess.run(kill, capture_output=True, text=True, encoding="utf-8", errors="replace")
time.sleep(4)

# 3) 用原命令行重启（首条作为重启命令）
if lines:
    subprocess.Popen(lines[0], shell=True)
    print("restarted with:", lines[0][:200])
else:
    print("WARN: no command line captured; ComfyUI may need manual restart via launcher")
