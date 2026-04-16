#!/bin/sh
# Container entrypoint — starts frpc (optional) then the CheckMK agent via socat.
#
# frpc activation — two modes (in order of priority):
#
# 1. Mounted config file (advanced / full control):
#      -v /etc/frp/frpc.toml:/etc/frp/frpc.toml:ro
#    Uses the file as-is. All values must be set inside the file.
#
# 2. Environment variables (simple / recommended):
#      -e FRPC_SERVER_ADDR=monitor.nethlab.it
#      -e FRPC_SERVER_PORT=7000          (optional, default: 7000)
#      -e FRPC_TOKEN=your-auth-token
#      -e FRPC_PROXY_NAME=myhost         (name shown on frp server)
#      -e FRPC_REMOTE_PORT=6003          (port assigned on frp server)
#      -e FRPC_TLS=true                  (optional, default: true)
#    A config is generated at /tmp/frpc-generated.toml and frpc is started.
#
# If neither a config file nor env vars are provided, frpc is skipped entirely
# and the container runs the CheckMK agent only (no tunneling).

FRPC_CONFIG="${FRPC_CONFIG:-/etc/frp/frpc.toml}"
FRPC_GENERATED="/tmp/frpc-generated.toml"

if [ -f "$FRPC_CONFIG" ]; then
    echo "[entrypoint] frpc config found at $FRPC_CONFIG — starting frpc"
    frpc -c "$FRPC_CONFIG" &

elif [ -n "$FRPC_SERVER_ADDR" ] && [ -n "$FRPC_TOKEN" ] && [ -n "$FRPC_PROXY_NAME" ] && [ -n "$FRPC_REMOTE_PORT" ]; then
    _port="${FRPC_SERVER_PORT:-7000}"
    _tls="${FRPC_TLS:-true}"
    cat > "$FRPC_GENERATED" <<EOF
serverAddr = "${FRPC_SERVER_ADDR}"
serverPort = ${_port}

auth.method = "token"
auth.token  = "${FRPC_TOKEN}"

transport.tls.enable = ${_tls}

log.to = "/proc/1/fd/1"
log.level = "info"

[[proxies]]
name        = "${FRPC_PROXY_NAME}"
type        = "tcp"
localIP     = "127.0.0.1"
localPort   = 6556
remotePort  = ${FRPC_REMOTE_PORT}
EOF
    echo "[entrypoint] frpc config generated for proxy '${FRPC_PROXY_NAME}' → ${FRPC_SERVER_ADDR}:${FRPC_REMOTE_PORT}"
    frpc -c "$FRPC_GENERATED" &

else
    echo "[entrypoint] frpc not configured — CheckMK agent only (no tunnel)"
fi

exec socat TCP-LISTEN:6556,reuseaddr,fork,keepalive EXEC:/usr/bin/check_mk_agent
