FROM rockylinux:9-minimal

# CheckMK server base URL and agent version — override at build time:
#   podman build --build-arg CMK_VERSION=2.4.0p27 -t checkmk-agent:test .
#   podman build --build-arg CMK_AGENT_URL=https://other-server/site/check_mk/agents -t checkmk-agent:test .
ARG CMK_AGENT_URL=https://YOUR_CHECKMK_SERVER/monitoring/check_mk/agents
ARG CMK_VERSION=2.4.0p26

# Install dependencies
RUN microdnf install -y \
    python3 \
    git \
    socat \
    curl \
    && microdnf clean all

# Install CheckMK agent from internal server (same version as server)
RUN curl -fsSL "${CMK_AGENT_URL}/check-mk-agent-${CMK_VERSION}-1.noarch.rpm" \
    -o /tmp/check-mk-agent.rpm && \
    rpm -ivh /tmp/check-mk-agent.rpm && \
    rm -f /tmp/check-mk-agent.rpm

# Clone checkmk-tools repository
RUN git clone https://github.com/nethesis/checkmk-tools.git /opt/checkmk-tools

# Deploy NS8 local checks (strip .py extension, set executable)
RUN for f in /opt/checkmk-tools/script-check-ns8/full/*.py; do \
        base=$(basename "$f" .py); \
        cp "$f" "/usr/lib/check_mk_agent/local/$base"; \
        chmod +x "/usr/lib/check_mk_agent/local/$base"; \
    done && \
    mv /usr/lib/check_mk_agent/local/monitor_podman_events \
       /usr/lib/check_mk_agent/local/check_podman_events

# Expose CheckMK agent port
EXPOSE 6556

# Run agent via socat on port 6556
# Note: Podman socket must be mounted at runtime:
#   -v /run/podman/podman.sock:/run/podman/podman.sock
ENTRYPOINT ["socat", "TCP-LISTEN:6556,reuseaddr,fork,keepalive", "EXEC:/usr/bin/check_mk_agent"]
