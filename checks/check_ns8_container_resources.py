#!/usr/bin/env python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NS8 container CPU/memory resources via Podman socket API (container-native, no runagent)

import json
import http.client
import os
import socket as _socket

SERVICE = "NS8.Container.Resources"
PODMAN_SOCK = "/run/podman/podman.sock"
CPU_WARN = 80.0
CPU_CRIT = 95.0
MEM_WARN = 80.0
MEM_CRIT = 95.0

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

def _pct(v):
    try:
        return min(float(v), 100.0)
    except:
        return 0.0

## Check

def check():
    if not os.path.exists(PODMAN_SOCK):
        print(f"2 {SERVICE} - CRITICAL: podman socket not found at {PODMAN_SOCK}")
        return

    data = _api("/containers/stats?stream=false")
    if data is None:
        print(f"2 {SERVICE} - CRITICAL: cannot reach podman socket")
        return

    stats = data.get("Stats") or []
    if not stats:
        print(f"0 {SERVICE} - OK: no containers running")
        return

    total = len(stats)
    warn = 0
    crit = 0
    cpu_list = []
    mem_list = []

    for s in stats:
        name = s.get("Name", "?")
        cpu = _pct(s.get("CPU", 0))
        mem = _pct(s.get("MemPerc", 0))
        cpu_list.append((name, cpu))
        mem_list.append((name, mem))
        if cpu >= CPU_CRIT or mem >= MEM_CRIT:
            crit += 1
        elif cpu >= CPU_WARN or mem >= MEM_WARN:
            warn += 1

    top_cpu = sorted(cpu_list, key=lambda x: x[1], reverse=True)[:3]
    top_mem = sorted(mem_list, key=lambda x: x[1], reverse=True)[:3]
    top_cpu_str = ", ".join(f"{n}:{v:.1f}%" for n, v in top_cpu)
    top_mem_str = ", ".join(f"{n}:{v:.1f}%" for n, v in top_mem)

    max_cpu = max(v for _, v in cpu_list) if cpu_list else 0.0
    max_mem = max(v for _, v in mem_list) if mem_list else 0.0

    state = 2 if crit > 0 else (1 if warn > 0 else 0)
    print(f"{state} {SERVICE} - total={total} warn={warn} crit={crit} top_cpu=[{top_cpu_str}] top_mem=[{top_mem_str}] | max_cpu={max_cpu:.2f};{CPU_WARN};{CPU_CRIT};0;100 max_mem={max_mem:.2f};{MEM_WARN};{MEM_CRIT};0;100")

check()
