FROM rockylinux:9-minimal

# CheckMK server base URL — REQUIRED at build time:
#   podman build --build-arg CMK_AGENT_URL=https://<checkmk-server>/<site>/check_mk/agents -t checkmk-agent:latest .
# The agent version is auto-detected from the server agents listing.
ARG CMK_AGENT_URL

# frpc version to embed — override at build time if needed:
#   podman build --build-arg FRP_VERSION=0.68.1 ...
ARG FRP_VERSION=0.68.1

# Install dependencies
RUN microdnf install -y \
    python3 \
    socat \
    curl \
    && microdnf clean all

# Install frpc (Fast Reverse Proxy client) — used only when /etc/frp/frpc.toml is mounted
RUN curl -fsSL "https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_amd64.tar.gz" \
    | tar -xz --strip-components=1 -C /usr/local/bin/ "frp_${FRP_VERSION}_linux_amd64/frpc" && \
    chmod +x /usr/local/bin/frpc

# Install CheckMK agent — version auto-detected from server agents listing
RUN set -e; \
    RPM_FILE=$(curl -fsSL "${CMK_AGENT_URL}/" \
        | grep -oE 'check-mk-agent-[0-9][^"]+\.noarch\.rpm' \
        | head -1); \
    [ -n "$RPM_FILE" ] || { echo "ERROR: could not detect agent RPM from ${CMK_AGENT_URL}/"; exit 1; }; \
    echo "Detected agent package: ${RPM_FILE}"; \
    curl -fsSL "${CMK_AGENT_URL}/${RPM_FILE}" -o /tmp/check-mk-agent.rpm && \
    rpm -ivh /tmp/check-mk-agent.rpm && \
    rm -f /tmp/check-mk-agent.rpm

# Deploy all local checks from checks/ (self-contained, no external git clone)
COPY checks/ /tmp/checks/
RUN for f in /tmp/checks/*.py; do \
        base=$(basename "$f" .py); \
        sed -i 's/\r//' "$f"; \
        cp "$f" "/usr/lib/check_mk_agent/local/$base"; \
        chmod +x "/usr/lib/check_mk_agent/local/$base"; \
    done && \
    rm -rf /tmp/checks

# Expose CheckMK agent port
EXPOSE 6556

# Entrypoint: starts frpc if /etc/frp/frpc.toml is mounted, then socat.
# Mount frpc config at runtime to enable the tunnel:
#   -v /etc/frp/frpc.toml:/etc/frp/frpc.toml:ro
# Override config path via env if needed:
#   -e FRPC_CONFIG=/path/to/frpc.toml
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
