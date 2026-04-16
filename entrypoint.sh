#!/bin/sh
# Container entrypoint — starts frpc (optional) then the CheckMK agent via socat.
#
# frpc is started only if a config file is present at /etc/frp/frpc.toml
# (or the path set in FRPC_CONFIG env var).
# Mount the config at runtime to enable the tunnel:
#   -v /etc/frp/frpc.toml:/etc/frp/frpc.toml:ro
#
# The config file format is standard frpc TOML (frp >= 0.50).
# Example minimal config:
#   serverAddr = "<frp-server-ip>"
#   serverPort = 7000
#   [[proxies]]
#   name = "checkmk-agent"
#   type = "tcp"
#   localIP = "127.0.0.1"
#   localPort = 6556
#   remotePort = <assigned-port>

FRPC_CONFIG="${FRPC_CONFIG:-/etc/frp/frpc.toml}"

if [ -f "$FRPC_CONFIG" ]; then
    echo "[entrypoint] frpc config found at $FRPC_CONFIG — starting frpc"
    frpc -c "$FRPC_CONFIG" &
else
    echo "[entrypoint] no frpc config at $FRPC_CONFIG — skipping frpc (CheckMK agent only)"
fi

exec socat TCP-LISTEN:6556,reuseaddr,fork,keepalive EXEC:/usr/bin/check_mk_agent
