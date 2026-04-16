#!/usr/bin/env python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NS8 container running status via Podman socket API (container-native, no runagent)

import json
import http.client
import os
import socket as _socket

SERVICE = "NS8.Container.Status"
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

## Check

def check():
    if not os.path.exists(PODMAN_SOCK):
        print(f"2 {SERVICE} - CRITICAL: podman socket not found at {PODMAN_SOCK}")
        return

    containers = _api("/containers/json?all=true")
    if containers is None:
        print(f"2 {SERVICE} - CRITICAL: cannot reach podman socket")
        return

    real = [c for c in containers if not c.get("IsInfra", False)]
    if not real:
        print(f"0 {SERVICE} - OK: no containers found")
        return

    # Exclude one-shot containers: exited with code 0 = completed successfully
    services = [c for c in real if not (c.get("State") == "exited" and c.get("ExitCode", 1) == 0)]
    total = len(services)
    stopped = [c for c in services if c.get("State") != "running"]

    if not stopped:
        print(f"0 {SERVICE} - OK: all containers running ({total}/{total})")
        return

    names = [c.get("Names", ["?"])[0].lstrip("/") for c in stopped]
    states = [c.get("State", "?") for c in stopped]
    detail = ", ".join(f"{n}({s})" for n, s in zip(names, states))
    print(f"2 {SERVICE} - CRITICAL: {len(stopped)}/{total} not running: {detail}")

check()
