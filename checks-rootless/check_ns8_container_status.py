#!/usr/bin/python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NS8 container running status via runagent (rootless, per-module)

import json
import subprocess

SERVICE = "NS8.Container.Status"

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

## Check

def check():
    modules = list_modules()
    if not modules:
        print(f"3 {SERVICE} - UNKNOWN: runagent not available or no modules found")
        return

    total = 0
    stopped = []

    for mod in modules:
        containers = podman_ps_json(mod)
        if containers is None:
            continue
        real = [c for c in containers if not c.get("IsInfra", False)]
        services = [c for c in real if not (c.get("State") == "exited" and c.get("ExitCode", 1) == 0)]
        total += len(services)
        for c in services:
            if c.get("State") != "running":
                name = (c.get("Names") or ["?"])[0].lstrip("/")
                stopped.append(f"{name}({c.get('State', '?')})")

    if not stopped:
        print(f"0 {SERVICE} - OK: all containers running ({total}/{total})")
        return

    detail = ", ".join(stopped)
    print(f"2 {SERVICE} - CRITICAL: {len(stopped)}/{total} not running: {detail}")

check()
