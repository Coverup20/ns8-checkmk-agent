#!/usr/bin/python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NS8 container CPU/memory resources via runagent (rootless, per-module)

import json
import subprocess

SERVICE = "NS8.Container.Resources"
CPU_WARN = 80.0
CPU_CRIT = 95.0
MEM_WARN = 80.0
MEM_CRIT = 95.0

## Utils

def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 1, "", str(e)

def list_modules():
    rc, out, _ = run(["runagent", "-l"])
    if rc != 0:
        return []
    return [l.strip() for l in out.splitlines() if l.strip()]

def podman_stats_json(module):
    rc, out, _ = run(["runagent", "-m", module, "podman", "stats", "--no-stream", "--format", "json"])
    if rc != 0 or not out.strip():
        return []
    try:
        data = json.loads(out)
        # podman stats --format json can return list or {"Stats":[...]}
        if isinstance(data, list):
            return data
        return data.get("Stats") or []
    except:
        return []

def pct(v):
    try:
        if isinstance(v, str):
            return min(float(v.rstrip("%")), 100.0)
        return min(float(v), 100.0)
    except:
        return 0.0

## Check

def check():
    modules = list_modules()
    if not modules:
        print(f"3 {SERVICE} - UNKNOWN: runagent not available or no modules found")
        return

    cpu_list = []
    mem_list = []

    for mod in modules:
        stats = podman_stats_json(mod)
        for s in stats:
            name = s.get("name") or s.get("Name") or "?"
            cpu = pct(s.get("cpu_percent") if "cpu_percent" in s else s.get("CPU", 0))
            mem = pct(s.get("mem_percent") if "mem_percent" in s else s.get("MemPerc", 0))
            cpu_list.append((name, cpu))
            mem_list.append((name, mem))

    if not cpu_list:
        print(f"0 {SERVICE} - OK: no containers running")
        return

    total = len(cpu_list)
    warn = 0
    crit = 0
    for _, cpu in cpu_list:
        idx = cpu_list.index((_, cpu))
        mem = mem_list[idx][1]
        if cpu >= CPU_CRIT or mem >= MEM_CRIT:
            crit += 1
        elif cpu >= CPU_WARN or mem >= MEM_WARN:
            warn += 1

    top_cpu = sorted(cpu_list, key=lambda x: x[1], reverse=True)[:3]
    top_mem = sorted(mem_list, key=lambda x: x[1], reverse=True)[:3]
    top_cpu_str = ", ".join(f"{n}:{v:.1f}%" for n, v in top_cpu)
    top_mem_str = ", ".join(f"{n}:{v:.1f}%" for n, v in top_mem)
    max_cpu = max(v for _, v in cpu_list)
    max_mem = max(v for _, v in mem_list)

    state = 2 if crit > 0 else (1 if warn > 0 else 0)
    print(f"{state} {SERVICE} - total={total} warn={warn} crit={crit} top_cpu=[{top_cpu_str}] top_mem=[{top_mem_str}] | max_cpu={max_cpu:.2f};{CPU_WARN};{CPU_CRIT};0;100 max_mem={max_mem:.2f};{MEM_WARN};{MEM_CRIT};0;100")

check()
