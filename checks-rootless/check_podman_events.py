#!/usr/bin/python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check recent Podman container events via runagent (rootless, per-module)

import json
import subprocess

SERVICE = "Podman.Events"
LOOKBACK = "15m"

CRITICAL_ACTIONS = {"oom"}
WARNING_ACTIONS = {"died", "exited"}

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

def get_events(module):
    rc, out, _ = run([
        "runagent", "-m", module,
        "podman", "events", "--stream=false",
        f"--since={LOOKBACK}",
        "--filter", "type=container",
        "--format", "json",
    ])
    if rc != 0 or not out.strip():
        return []
    events = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except:
            pass
    return events

## Check

def check():
    modules = list_modules()
    if not modules:
        print(f"3 {SERVICE} - UNKNOWN: runagent not available or no modules found")
        return

    crits = []
    warns = []

    for mod in modules:
        for ev in get_events(mod):
            action = (ev.get("Action") or ev.get("status") or "").lower()
            actor = ev.get("Actor") or ev.get("actor") or {}
            attrs = actor.get("Attributes") or actor.get("attributes") or {}
            name = attrs.get("name") or actor.get("ID", "?")[:12]

            if action == "exited":
                exit_code = int(attrs.get("exitCode") or attrs.get("exit_code") or 0)
                if exit_code == 0:
                    continue

            if action in CRITICAL_ACTIONS:
                crits.append(f"{name}({action})")
            elif action in WARNING_ACTIONS:
                warns.append(f"{name}({action})")

    if crits:
        detail = ", ".join(crits[:5])
        print(f"2 {SERVICE} - CRITICAL: {len(crits)} event(s) in last 15m: {detail}")
        return

    if warns:
        detail = ", ".join(warns[:5])
        print(f"1 {SERVICE} - WARNING: {len(warns)} event(s) in last 15m: {detail}")
        return

    print(f"0 {SERVICE} - OK: no critical events in last 15m")

check()
