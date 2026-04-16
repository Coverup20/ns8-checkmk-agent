#!/usr/bin/env python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NS8 container inventory via Podman socket API (container-native, no runagent)

import json
import http.client
import os
import socket as _socket

SERVICE = "NS8.Container.Inventory"
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
    # Exclude one-shot containers: exited with code 0 = completed successfully
    services = [c for c in real if not (c.get("State") == "exited" and c.get("ExitCode", 1) == 0)]
    total = len(services)
    running = sum(1 for c in services if c.get("State") == "running")
    stopped = total - running

    names = []
    for c in services:
        raw_name = c.get("Names", ["?"])[0].lstrip("/")
        image = c.get("Image", "").split("/")[-1].split(":")[0]
        names.append(f"{raw_name}:{image}")

    names_str = ", ".join(names) if names else "none"
    print(f"0 {SERVICE} - OK: total={total} running={running} stopped={stopped} | total={total} running={running} stopped={stopped}; {names_str}")

check()
