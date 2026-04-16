#!/usr/bin/python3
#
# Copyright (C) 2025 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-2.0-only
#

# Interactive deployment helper for ns8-checkmk-agent.
# Guides through variant selection, frpc configuration,
# and generates (or executes via SSH) the podman run command.

import sys
import subprocess
import shlex

VERSION = "1.0.0"

## Utils

def ask(prompt, default=None):
    suffix = f" [{default}]" if default is not None else ""
    val = input(f"{prompt}{suffix}: ").strip()
    if not val and default is not None:
        return str(default)
    return val

def ask_yn(prompt, default="y"):
    marker = "Y/n" if default == "y" else "y/N"
    val = input(f"{prompt} [{marker}]: ").strip().lower()
    if not val:
        return default == "y"
    return val in ("y", "yes", "si", "s")

def ask_choice(prompt, choices, default=None):
    for i, (label, desc) in enumerate(choices, 1):
        marker = " (default)" if str(default) == str(i) else ""
        print(f"  {i}) {label:12} — {desc}{marker}")
    while True:
        val = ask(prompt, default)
        try:
            idx = int(val) - 1
            if 0 <= idx < len(choices):
                return choices[idx][0]
        except (ValueError, TypeError):
            pass
        print(f"  Enter a number between 1 and {len(choices)}")

def run_ssh(host, command):
    print(f"\n[deploy] Running on {host}...")
    rc = subprocess.run(["ssh", host, command]).returncode
    return rc

## Deploy

def choose_variant():
    print("\nSelect image variant:")
    tag = ask_choice("Variant", [
        ("latest",   "minimal — system checks + SOS only"),
        ("runagent", "full NS8 — module inspection, NethVoice, WebTop, mail..."),
    ], default=2)
    return tag

def ask_frpc():
    if not ask_yn("\nEnable frpc tunnel (to reach the agent from the CheckMK server)?", "n"):
        return {}
    print()
    params = {
        "FRPC_SERVER_ADDR": ask("  FRPC_SERVER_ADDR  (frp server hostname)", "monitor.nethlab.it"),
        "FRPC_SERVER_PORT": ask("  FRPC_SERVER_PORT", "7000"),
        "FRPC_TOKEN":       ask("  FRPC_TOKEN        (auth token)"),
        "FRPC_PROXY_NAME":  ask("  FRPC_PROXY_NAME   (unique name for this host, e.g. rl94ns8)"),
        "FRPC_REMOTE_PORT": ask("  FRPC_REMOTE_PORT  (port assigned on frp server, e.g. 6020)"),
    }
    tls = ask("  FRPC_TLS", "true")
    if tls != "true":
        params["FRPC_TLS"] = tls
    return params

def build_run_cmd(tag, container_name, frpc_env):
    has_frpc = bool(frpc_env)
    lines = [
        "podman run -d",
        f"  --name {container_name}",
        "  --restart unless-stopped",
        "  --privileged --pid=host --cgroupns=host",
        "  --security-opt label=disable",
    ]

    # Expose port 6556 only if frpc is NOT configured (direct access mode).
    # With frpc the tunnel handles connectivity — binding 6556 may conflict
    # with a native check-mk-agent already listening on the host.
    if not has_frpc:
        lines.append("  -p 6556:6556")

    for k, v in frpc_env.items():
        lines.append(f"  -e {k}={shlex.quote(v)}")

    if tag == "runagent":
        lines += [
            "  -v /usr/local/agent:/usr/local/agent:ro",
            "  -v /usr/local/bin/runagent:/usr/local/bin/runagent:ro",
            "  -v /usr/bin/podman:/usr/bin/podman:ro",
            "  -v /usr/bin/python3.11:/usr/bin/python3.11:ro",
            "  -v /usr/lib64/libpython3.11.so.1.0:/usr/lib64/libpython3.11.so.1.0:ro",
            "  -v /usr/lib64/python3.11:/usr/lib64/python3.11:ro",
            "  -v /etc/passwd:/etc/passwd:ro",
            "  -v /etc/group:/etc/group:ro",
            "  -v /etc/shadow:/etc/shadow:ro",
            "  -v /etc/nethserver:/etc/nethserver:ro",
            "  -v /run/user:/run/user:rw",
            "  -v /home:/home:ro",
        ]

    lines.append(f"  localhost/checkmk-agent:{tag}")
    return " \\\n".join(lines)

def main():
    print(f"\nns8-checkmk-agent deploy helper  v{VERSION}")
    print("=" * 52)

    tag            = choose_variant()
    container_name = ask("\nContainer name", "checkmk-agent")
    frpc_env       = ask_frpc()
    cmd            = build_run_cmd(tag, container_name, frpc_env)

    print("\n" + "=" * 52)
    print("Generated command:\n")
    print(cmd)
    print("=" * 52)

    if not ask_yn("\nExecute via SSH on a remote host now?", "n"):
        print("\nCopy the command above and run it on the target host manually.")
        return

    host = ask("SSH host alias (from ~/.ssh/config)")
    cmk_url = ask("CheckMK agents URL (needed if image must be built)", "https://monitor.nethlab.it/monitoring/check_mk/agents")

    # Check if image exists on remote host, build if needed
    check = subprocess.run(
        ["ssh", host, f"podman image exists localhost/checkmk-agent:{tag} && echo EXISTS || echo MISSING"],
        capture_output=True, text=True
    )
    if "MISSING" in check.stdout:
        print(f"\n[deploy] Image checkmk-agent:{tag} not found on {host} — building now...")
        build_cmd = (
            f"cd /opt/ns8-checkmk-agent && "
            f"git fetch origin && git reset --hard origin/main && "
            f"podman build -f Dockerfile{'.runagent' if tag == 'runagent' else ''} "
            f"--build-arg CMK_AGENT_URL={cmk_url} "
            f"-t checkmk-agent:{tag} . "
            f"2>&1 | tail -5"
        )
        rc = run_ssh(host, build_cmd)
        if rc != 0:
            print(f"\n[deploy] ERROR: build failed (exit {rc})")
            sys.exit(1)
    else:
        print(f"\n[deploy] Image checkmk-agent:{tag} already present on {host}")

    if ask_yn(f"Stop and remove existing '{container_name}' first?", "y"):
        run_ssh(host, f"podman stop {container_name} 2>/dev/null; podman rm {container_name} 2>/dev/null; echo 'old container removed'")

    rc = run_ssh(host, cmd)
    if rc != 0:
        print(f"\n[deploy] ERROR: podman run exited with code {rc}")
        sys.exit(1)

    print("\n[deploy] Container started — fetching logs...")
    run_ssh(host, f"sleep 4 && podman logs {container_name}")

main()
