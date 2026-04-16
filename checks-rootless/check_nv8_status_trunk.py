#!/usr/bin/python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NethVoice trunk status via runagent + podman exec into Asterisk

import json
import re
import subprocess

SERVICE_PREFIX = "NV8.Status.Trunk"
SERVICE_SUMMARY = "NV8.Status.Trunks"

STATE_MAP = {
    "Registered":     0,
    "Not Registered": 1,
    "Trying":         1,
    "No Auth":        2,
    "Rejected":       2,
    "Failed":         2,
    "Stopped":        2,
    "Unregistered":   2,
}

STATUS_RE = re.compile(
    r"\b(Not\s+Registered|No\s+Auth|Registered|Trying|Rejected|Failed|Stopped|Unregistered)\b",
    re.IGNORECASE,
)

## Utils

def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 1, "", str(e)

def list_modules():
    rc, out, _ = run(["runagent", "-l"])
    if rc != 0:
        return []
    return [l.strip() for l in out.splitlines() if l.strip()]

def podman_ps_json(module):
    rc, out, _ = run(["runagent", "-m", module, "podman", "ps", "--all", "--format", "json"])
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except:
        return None

def find_asterisk_name(containers):
    for c in containers:
        if c.get("IsInfra", False) or c.get("State") != "running":
            continue
        for n in (c.get("Names") or []):
            if "asterisk" in n.lower() or "freepbx" in n.lower():
                return n.lstrip("/")
    return None

def exec_asterisk(module, container_name, cmd_str):
    rc, out, _ = run(["runagent", "-m", module, "podman", "exec", container_name, "asterisk", "-rx", cmd_str])
    if rc != 0:
        return None
    return out

## Check

def check():
    modules = list_modules()
    voice_modules = [m for m in modules if "nethvoice" in m or "freepbx" in m]

    if not voice_modules:
        print(f"0 {SERVICE_SUMMARY} - NethVoice not installed")
        return

    for mod in voice_modules:
        containers = podman_ps_json(mod)
        if containers is None:
            print(f"3 {SERVICE_SUMMARY} - UNKNOWN: cannot query podman for {mod}")
            continue

        cname = find_asterisk_name(containers)
        if not cname:
            print(f"0 {SERVICE_SUMMARY} - NethVoice not installed (no Asterisk container found)")
            continue

        output = exec_asterisk(mod, cname, "pjsip show registrations")
        if output is None:
            print(f"3 {SERVICE_SUMMARY} - UNKNOWN: exec into Asterisk container failed")
            continue

        trunks = {}
        for line in output.splitlines():
            m = STATUS_RE.search(line)
            if not m:
                continue
            status_str = m.group(1).strip()
            parts = line.strip().split()
            trunk_name = parts[0] if parts else "unknown"
            trunks[trunk_name] = status_str

        if not trunks:
            print(f"0 {SERVICE_SUMMARY} - OK: no trunks configured")
            continue

        total = len(trunks)
        ok = sum(1 for s in trunks.values() if STATE_MAP.get(s, 0) == 0)
        warn = sum(1 for s in trunks.values() if STATE_MAP.get(s, 0) == 1)
        crit_count = sum(1 for s in trunks.values() if STATE_MAP.get(s, 0) == 2)

        for name, st in trunks.items():
            state = STATE_MAP.get(st, 3)
            print(f"{state} {SERVICE_PREFIX}.{name} - {st}")

        overall = 2 if crit_count > 0 else (1 if warn > 0 else 0)
        print(f"{overall} {SERVICE_SUMMARY} - total={total} ok={ok} warn={warn} crit={crit_count}")

check()
