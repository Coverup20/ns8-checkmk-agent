#!/usr/bin/python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check WebTop availability on NS8 via runagent + HTTP probe
# Uses runagent to inspect rootless webtop module containers

import json
import socket as _socket
import ssl
import subprocess
import urllib.request
import urllib.error

SERVICE = "Webtop5"

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

def get_domain():
    try:
        fqdn = _socket.getfqdn()
        parts = fqdn.split(".", 1)
        return parts[1] if len(parts) > 1 else None
    except:
        return None

def http_check(url):
    try:
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10, context=ctx) as r:
            return 0, r.getcode()
    except urllib.error.HTTPError as e:
        return 2, e.code
    except:
        return 2, 0

## Check

def check():
    modules = list_modules()
    webtop_modules = sorted(m for m in modules if m.startswith("webtop"))

    if not webtop_modules:
        print(f"0 {SERVICE} - WebTop not installed")
        return

    domain = get_domain()

    for mod in webtop_modules:
        svc = f"{SERVICE}.{mod}"
        containers = podman_ps_json(mod)
        if containers is None:
            print(f"2 {svc} - CRITICAL: cannot query podman for {mod}")
            continue

        real = [c for c in containers if not c.get("IsInfra", False)]
        if not real:
            print(f"0 {svc} - no containers (module not running)")
            continue

        stopped = [c for c in real if c.get("State") != "running"]
        if stopped:
            names = ", ".join((c.get("Names") or ["?"])[0] for c in stopped)
            print(f"2 {svc} - CRITICAL: container(s) not running: {names}")
            continue

        count = len(real)
        if domain:
            url = f"https://webtop.{domain}/webtop/"
            state, code = http_check(url)
            if state == 0:
                print(f"0 {svc} - OK: {count} containers running, HTTP {code}")
            else:
                http_info = f"HTTP {code}" if code else "connection error"
                print(f"1 {svc} - WARNING: {count} containers running but HTTP check failed ({http_info})")
        else:
            print(f"0 {svc} - OK: {count} containers running")

check()
