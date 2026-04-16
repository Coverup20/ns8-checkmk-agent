#!/usr/bin/env python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NS8 mail services (dovecot, postfix, clamav, rspamd) via Podman socket API
# Container-native version: uses podman socket instead of runagent

import json
import http.client
import os
import socket as _socket

SERVICE = "NS8.Mail"
PODMAN_SOCK = "/run/podman/podman.sock"
TARGET_SERVICES = ["clamav", "rspamd", "dovecot", "postfix"]
LOG_LINES = 500

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
    out = b""
    i = 0
    while i + 8 <= len(raw):
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        out += raw[i + 8:i + 8 + size]
        i += 8 + size
    return out.decode("utf-8", errors="replace")

def exec_in_container(container_id, cmd):
    """Run cmd (list) inside container, return stdout string or None."""
    status, raw = _api_post(f"/containers/{container_id}/exec", {
        "AttachStdout": True,
        "AttachStderr": False,
        "Cmd": cmd,
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

def match_service(names, svc):
    """Return True if any container name contains the service keyword."""
    for n in names:
        if svc in n.lower():
            return True
    return False

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

    # Find mail-related containers (names contain service keywords)
    mail_containers = {}
    for c in real:
        names = c.get("Names", [])
        for svc in TARGET_SERVICES:
            if match_service(names, svc) and svc not in mail_containers:
                mail_containers[svc] = c

    if not mail_containers:
        # No mail module installed — silent exit (no output)
        return

    for svc in TARGET_SERVICES:
        c = mail_containers.get(svc)
        if c is None:
            print(f"3 {svc} - {svc} not found")
            continue

        state = c.get("State", "")
        cid = c.get("Id", "")

        if state == "running":
            print(f"0 {svc} - {svc} active")

            if svc == "dovecot":
                # IMAP sessions
                out = exec_in_container(cid, ["doveadm", "who"])
                if out is not None:
                    sessions = len([l for l in out.strip().splitlines() if l.strip()])
                    if sessions > 0:
                        print(f"0 imap_sessions - Active IMAP sessions: {sessions}")
                    else:
                        print(f"1 imap_sessions - No active IMAP sessions")
                else:
                    print(f"3 imap_sessions - Cannot query doveadm")

                # vsz_limit errors in logs
                shell_cmd = (
                    f"tail -n {LOG_LINES} /var/log/dovecot* 2>/dev/null | "
                    "grep -c 'Cannot allocate memory due to vsz_limit' || true"
                )
                out2 = exec_in_container(cid, ["sh", "-c", shell_cmd])
                try:
                    error_count = int(out2.strip()) if out2 else 0
                except:
                    error_count = 0

                if error_count > 0:
                    print(f"2 dovecot_vszlimit - CRIT: vsz_limit errors in logs ({error_count} occurrences)")
                else:
                    print(f"0 dovecot_vszlimit - No vsz_limit errors in logs")
        else:
            print(f"2 {svc} - {svc} not active (state: {state})")

check()
