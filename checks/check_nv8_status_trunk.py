#!/usr/bin/env python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NethVoice trunk status via Podman exec into Asterisk container
# Container-native version: uses podman socket instead of runagent

import json
import http.client
import os
import re
import socket as _socket

VERSION = "2.0.0"
SERVICE_PREFIX = "NV8.Status.Trunk"
SERVICE_SUMMARY = "NV8.Status.Trunks"
PODMAN_SOCK = "/run/podman/podman.sock"

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
        raw = r.read()
        return r.status, raw
    except:
        return 0, b""

def _parse_mux(raw):
    """Parse Docker/podman multiplexed stdout stream."""
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

    output = exec_asterisk(cid, "pjsip show registrations")
    if output is None:
        print(f"3 {SERVICE_SUMMARY} - UNKNOWN: exec into Asterisk container failed")
        return

    trunks = {}
    for line in output.splitlines():
        m = STATUS_RE.search(line)
        if not m:
            continue
        status_str = m.group(1).strip()
        # Extract trunk name (first non-empty token before status)
        parts = line.strip().split()
        trunk_name = parts[0] if parts else "unknown"
        trunks[trunk_name] = status_str

    if not trunks:
        print(f"0 {SERVICE_SUMMARY} - OK: no trunks configured")
        return

    total = len(trunks)
    ok = sum(1 for s in trunks.values() if STATE_MAP.get(s, 0) == 0)
    warn = sum(1 for s in trunks.values() if STATE_MAP.get(s, 0) == 1)
    crit_count = sum(1 for s in trunks.values() if STATE_MAP.get(s, 0) == 2)

    # One line per trunk
    for name, st in trunks.items():
        state = STATE_MAP.get(st, 3)
        print(f"{state} {SERVICE_PREFIX}.{name} - {st}")

    # Summary line
    overall = 2 if crit_count > 0 else (1 if warn > 0 else 0)
    print(f"{overall} {SERVICE_SUMMARY} - total={total} ok={ok} warn={warn} crit={crit_count}")

check()
