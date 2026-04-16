#!/usr/bin/env python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check WebTop availability on NS8 via Podman socket + HTTP probe
# Container-native version: uses podman socket instead of runagent

import json
import http.client
import os
import socket as _socket
import ssl
import urllib.request
import urllib.error

SERVICE = "Webtop5"
PODMAN_SOCK = "/run/podman/podman.sock"

## Utils

class _UnixConn(http.client.HTTPConnection):
    def connect(self):
        self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        self.sock.connect(PODMAN_SOCK)

def _api(path):
    try:
        c = _UnixConn("d")
        c.request("GET", f"/v4.0.0/libpod{path}")
        r = c.getresponse()
        return json.loads(r.read()) if r.status == 200 else None
    except:
        return None

def find_webtop_containers(containers):
    found = []
    for c in containers:
        if c.get("IsInfra", False):
            continue
        for n in c.get("Names", []):
            if "webtop" in n.lower():
                found.append(c)
                break
    return found

def get_domain():
    try:
        fqdn = _socket.getfqdn()
        parts = fqdn.split(".", 1)
        return parts[1] if len(parts) > 1 else None
    except:
        return None

def http_check(url):
    """Return (state, http_code): 0=OK, 2=CRIT"""
    try:
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            code = resp.getcode()
            return (0, code) if code == 200 else (2, code)
    except urllib.error.HTTPError as e:
        return 2, e.code
    except:
        return 2, 0

## Check

def check():
    if not os.path.exists(PODMAN_SOCK):
        print(f"2 {SERVICE} - CRITICAL: podman socket not found at {PODMAN_SOCK}")
        return

    containers = _api("/containers/json?all=true")
    if containers is None:
        print(f"2 {SERVICE} - CRITICAL: cannot reach podman socket")
        return

    webtop_containers = find_webtop_containers(containers)
    if not webtop_containers:
        print(f"0 {SERVICE} - WebTop not installed (no webtop container found)")
        return

    # Check any stopped webtop container
    stopped = [c for c in webtop_containers if c.get("State") != "running"]
    if stopped:
        names = ", ".join(c.get("Names", ["?"])[0] for c in stopped)
        print(f"2 {SERVICE} - CRITICAL: webtop container(s) not running: {names}")
        return

    # HTTP reachability check
    domain = get_domain()
    if not domain:
        print(f"1 {SERVICE} - cannot determine domain from FQDN for HTTP check")
        return

    url = f"https://webtop.{domain}/webtop/"
    state, code = http_check(url)

    if state == 0:
        print(f"0 {SERVICE} - WebTop responding at {url} (HTTP {code})")
    elif code == 0:
        print(f"2 {SERVICE} - WebTop NOT responding at {url} (connection error)")
    else:
        print(f"2 {SERVICE} - WebTop NOT responding at {url} (HTTP {code})")

check()
