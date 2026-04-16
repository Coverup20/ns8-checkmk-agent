#!/usr/bin/python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NS8 container inventory via runagent (rootless, per-module)

import json
import subprocess

SERVICE = "NS8.Container.Inventory"

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
    names = []

    for mod in modules:
        containers = podman_ps_json(mod)
        if containers is None:
            continue
        real = [c for c in containers if not c.get("IsInfra", False)]
        services = [c for c in real if not (c.get("State") == "exited" and c.get("ExitCode", 1) == 0)]
        for c in services:
            total += 1
            if c.get("State") == "running":
                running += 1
            raw_name = (c.get("Names") or ["?"])[0].lstrip("/")
            image = c.get("Image", "").split("/")[-1].split(":")[0]
            names.append(f"{raw_name}:{image}")

    stopped = total - running
    names_str = ", ".join(names) if names else "none"
    print(f"0 {SERVICE} - OK: total={total} running={running} stopped={stopped} | total={total} running={running} stopped={stopped}; {names_str}")

check()
