#!/usr/bin/python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check recent Podman container events via Podman socket API
# Replaces monitor_podman_events.py daemon — this is a proper local check

import json
import http.client
import os
import socket as _socket
import time

SERVICE = "Podman.Events"
PODMAN_SOCK = "/run/podman/podman.sock"
LOOKBACK_SECONDS = 900  # last 15 minutes

CRITICAL_ACTIONS = {"oom"}
WARNING_ACTIONS = {"died", "exited"}

## Utils

class _UnixConn(http.client.HTTPConnection):
    def connect(self):
        self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        self.sock.connect(PODMAN_SOCK)

def _get_events(since_ts):
    try:
        c = _UnixConn("d")
        c.request("GET", f"/v4.0.0/libpod/events?stream=false&since={since_ts}&filters=type%3Dcontainer")
        r = c.getresponse()
        raw = r.read().decode("utf-8", errors="replace")
        events = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except:
                pass
        return events
    except:
        return None

## Check

def check():
    if not os.path.exists(PODMAN_SOCK):
        print(f"2 {SERVICE} - CRITICAL: podman socket not found at {PODMAN_SOCK}")
        return

    since = int(time.time()) - LOOKBACK_SECONDS
    events = _get_events(since)
    if events is None:
        print(f"2 {SERVICE} - CRITICAL: cannot reach podman socket")
        return

    crits = []
    warns = []
    for ev in events:
        action = (ev.get("Action") or ev.get("status") or "").lower()
        name = ""
        actor = ev.get("Actor") or ev.get("actor") or {}
        attrs = actor.get("Attributes") or actor.get("attributes") or {}
        name = attrs.get("name") or actor.get("ID", "?")[:12]

        # Skip normal exits (exit code 0)
        if action == "exited":
            exit_code = int(attrs.get("exitCode", attrs.get("exit_code", 1)) or 1)
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
