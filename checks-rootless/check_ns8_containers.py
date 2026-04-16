#!/usr/bin/python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NS8 container count via runagent (rootless, per-module)

import json
import subprocess

SERVICE = "NS8.Containers"

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
    running = 0

    for mod in modules:
        containers = podman_ps_json(mod)
        if containers is None:
            continue
        real = [c for c in containers if not c.get("IsInfra", False)]
        services = [c for c in real if not (c.get("State") == "exited" and c.get("ExitCode", 1) == 0)]
        total += len(services)
        running += sum(1 for c in services if c.get("State") == "running")

    problem = total - running
    state = 2 if problem > 0 else 0
    print(f"{state} {SERVICE} - total={total} running={running} problem={problem}")

check()
