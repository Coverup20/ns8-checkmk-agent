#!/usr/bin/python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NethVoice extension registration status via runagent + podman exec into Asterisk

import json
import re
import subprocess

SERVICE_SUMMARY = "NV8.Status.Extensions"
WARN_PCT = 10.0
CRIT_PCT = 30.0

REGISTERED_STATES = {"not in use", "in use", "ringing", "ring", "busy", "on hold"}

ENDPOINT_RE = re.compile(
    r"^\s+Endpoint:\s+(\S+)\s+(.*?)\s+\d+\s+of\s+",
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

def parse_endpoints(output):
    endpoints = {}
    for line in output.splitlines():
        m = ENDPOINT_RE.match(line)
        if not m:
            continue
        name = m.group(1).split("/")[0]
        if name.lower() == "anonymous":
            continue
        state = m.group(2).strip().lower()
        endpoints[name] = state
    return endpoints

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

        output = exec_asterisk(mod, cname, "pjsip show endpoints")
        if output is None:
            print(f"3 {SERVICE_SUMMARY} - UNKNOWN: exec into Asterisk container failed")
            continue

        endpoints = parse_endpoints(output)
        if not endpoints:
            print(f"0 {SERVICE_SUMMARY} - OK: no endpoints configured")
            continue

        total = len(endpoints)
        unreg = {n: s for n, s in endpoints.items() if s not in REGISTERED_STATES}
        unreg_count = len(unreg)
        unreg_pct = (unreg_count / total * 100) if total > 0 else 0.0

        state = 2 if unreg_pct >= CRIT_PCT else (1 if unreg_pct >= WARN_PCT else 0)
        label = "CRITICAL" if state == 2 else ("WARNING" if state == 1 else "OK")

        if unreg:
            detail = ", ".join(f"{n}({s})" for n, s in list(unreg.items())[:5])
            print(f"{state} {SERVICE_SUMMARY} - {label}: {unreg_count}/{total} not registered ({unreg_pct:.1f}%) - {detail}")
        else:
            print(f"0 {SERVICE_SUMMARY} - OK: all {total} extensions registered")

check()
