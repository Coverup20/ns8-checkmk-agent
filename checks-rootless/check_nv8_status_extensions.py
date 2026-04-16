#!/usr/bin/env python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NethVoice extension registration status via Podman exec into Asterisk container
# Container-native version: uses podman socket instead of runagent

import json
import http.client
import os
import re
import socket as _socket

VERSION = "2.0.0"
SERVICE_SUMMARY = "NV8.Status.Extensions"
PODMAN_SOCK = "/run/podman/podman.sock"
WARN_PCT = 10.0
CRIT_PCT = 30.0

REGISTERED_STATES = {"not in use", "in use", "ringing", "ring", "busy", "on hold"}

ENDPOINT_RE = re.compile(
    r"^\s+Endpoint:\s+(\S+)\s+(.*?)\s+\d+\s+of\s+",
    re.IGNORECASE,
)

## Utils

class _UnixConn(http.client.HTTPConnection):
    def connect(self):
        self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        self.sock.connect(PODMAN_SOCK)

def _api_get(path):
    try:
        c = _UnixConn("d")
        c.request("GET", f"/v4.0.0/libpod{path}")
        r = c.getresponse()
        return json.loads(r.read()) if r.status == 200 else None
    except:
        return None

def _api_post(path, body):
    try:
        data = json.dumps(body).encode()
        c = _UnixConn("d")
        c.request("POST", f"/v4.0.0/libpod{path}", body=data,
                  headers={"Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, r.read()
    except:
        return 0, b""

def _parse_mux(raw):
    out = b""
    i = 0
    while i + 8 <= len(raw):
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        out += raw[i + 8:i + 8 + size]
        i += 8 + size
    return out.decode("utf-8", errors="replace")

def find_asterisk_container(containers):
    for c in containers:
        if c.get("IsInfra", False):
            continue
        if c.get("State") != "running":
            continue
        for n in c.get("Names", []):
            if "asterisk" in n.lower() or "freepbx" in n.lower():
                return c.get("Id", "")
    return None

def exec_asterisk(container_id, cmd_str):
    status, raw = _api_post(f"/containers/{container_id}/exec", {
        "AttachStdout": True,
        "AttachStderr": False,
        "Cmd": ["asterisk", "-rx", cmd_str],
    })
    if status != 201:
        return None
    try:
        exec_id = json.loads(raw)["Id"]
    except:
        return None

    status2, raw2 = _api_post(f"/exec/{exec_id}/start", {"Detach": False})
    if status2 not in (200, 101):
        return None
    return _parse_mux(raw2)

def parse_endpoints(output):
    endpoints = {}
    for line in output.splitlines():
        m = ENDPOINT_RE.match(line)
        if not m:
            continue
        name = m.group(1).split("/")[0]
        state = m.group(2).strip().lower()
        endpoints[name] = state
    return endpoints

## Check

def check():
    if not os.path.exists(PODMAN_SOCK):
        print(f"2 {SERVICE_SUMMARY} - CRITICAL: podman socket not found at {PODMAN_SOCK}")
        return

    containers = _api_get("/containers/json?all=true")
    if containers is None:
        print(f"2 {SERVICE_SUMMARY} - CRITICAL: cannot reach podman socket")
        return

    cid = find_asterisk_container(containers)
    if not cid:
        print(f"0 {SERVICE_SUMMARY} - NethVoice not installed (no Asterisk container found)")
        return

    output = exec_asterisk(cid, "pjsip show endpoints")
    if output is None:
        print(f"3 {SERVICE_SUMMARY} - UNKNOWN: exec into Asterisk container failed")
        return

    endpoints = parse_endpoints(output)
    if not endpoints:
        print(f"0 {SERVICE_SUMMARY} - OK: no endpoints configured")
        return

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
