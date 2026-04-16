#!/usr/bin/python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Check NS8 mail services (dovecot, postfix, clamav, rspamd) via runagent

import json
import subprocess

TARGET_SERVICES = ["clamav", "rspamd", "dovecot", "postfix"]
LOG_LINES = 500

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

def podman_exec(module, container_name, cmd_list):
    rc, out, _ = run(["runagent", "-m", module, "podman", "exec", container_name] + cmd_list)
    if rc != 0:
        return None
    return out

def match_service(names, svc):
    return any(svc in n.lower() for n in names)

## Check

def check():
    modules = list_modules()
    mail_modules = [m for m in modules if m.startswith("mail")]

    if not mail_modules:
        # No mail module installed — silent exit (no output)
        return

    for mod in mail_modules:
        containers = podman_ps_json(mod)
        if containers is None:
            continue
        real = [c for c in containers if not c.get("IsInfra", False)]

        mail_containers = {}
        for c in real:
            names = c.get("Names") or []
            for svc in TARGET_SERVICES:
                if match_service(names, svc) and svc not in mail_containers:
                    mail_containers[svc] = c

        if not mail_containers:
            continue

        for svc in TARGET_SERVICES:
            c = mail_containers.get(svc)
            if c is None:
                print(f"3 {svc} - {svc} not found")
                continue

            state = c.get("State", "")
            cname = (c.get("Names") or ["?"])[0].lstrip("/")

            if state == "running":
                print(f"0 {svc} - {svc} active")

                if svc == "dovecot":
                    # IMAP sessions
                    out = podman_exec(mod, cname, ["doveadm", "who"])
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
                    out2 = podman_exec(mod, cname, ["sh", "-c", shell_cmd])
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
