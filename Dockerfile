FROM rockylinux:9-minimal

# CheckMK server base URL — override at build time if needed:
#   podman build --build-arg CMK_AGENT_URL=https://other-server/site/check_mk/agents -t checkmk-agent:test .
# The agent version is auto-detected from the server listing — no need to hardcode it.
ARG CMK_AGENT_URL=https://YOUR_CHECKMK_SERVER/monitoring/check_mk/agents

# Install dependencies
RUN microdnf install -y \
    python3 \
    git \
    socat \
    curl \
    && microdnf clean all

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

# Clone checkmk-tools repository (base scripts: smoke_test, sos, webtop, etc.)
RUN git clone https://github.com/nethesis/checkmk-tools.git /opt/checkmk-tools

# Deploy base NS8 local checks from checkmk-tools (strip .py extension, set executable)
RUN for f in /opt/checkmk-tools/script-check-ns8/full/*.py; do \
        base=$(basename "$f" .py); \
        cp "$f" "/usr/lib/check_mk_agent/local/$base"; \
        chmod +x "/usr/lib/check_mk_agent/local/$base"; \
    done && \
    rm -f /usr/lib/check_mk_agent/local/monitor_podman_events

# Copy container-native checks (override runagent-based versions from checkmk-tools)
COPY checks/ /tmp/checks/
RUN for f in /tmp/checks/*.py; do \
        base=$(basename "$f" .py); \
        cp "$f" "/usr/lib/check_mk_agent/local/$base"; \
        chmod +x "/usr/lib/check_mk_agent/local/$base"; \
    done && \
    rm -rf /tmp/checks

# Expose CheckMK agent port
EXPOSE 6556

# Run agent via socat on port 6556
# Note: Podman socket must be mounted at runtime:
#   -v /run/podman/podman.sock:/run/podman/podman.sock
ENTRYPOINT ["socat", "TCP-LISTEN:6556,reuseaddr,fork,keepalive", "EXEC:/usr/bin/check_mk_agent"]
