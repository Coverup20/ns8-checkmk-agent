FROM rockylinux:9-minimal

# CheckMK server base URL — REQUIRED at build time:
#   podman build --build-arg CMK_AGENT_URL=https://<checkmk-server>/<site>/check_mk/agents -t checkmk-agent:latest .
# The agent version is auto-detected from the server agents listing.
ARG CMK_AGENT_URL

# Install dependencies
RUN microdnf install -y \
    python3 \
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

# Run agent via socat on port 6556
# Note: Podman socket must be mounted at runtime:
#   -v /run/podman/podman.sock:/run/podman/podman.sock
ENTRYPOINT ["socat", "TCP-LISTEN:6556,reuseaddr,fork,keepalive", "EXEC:/usr/bin/check_mk_agent"]
