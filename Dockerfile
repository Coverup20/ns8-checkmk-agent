FROM rockylinux:9-minimal

# CheckMK server base URL — override at build time if needed:
#   podman build --build-arg CMK_AGENT_URL=https://other-server/site/check_mk/agents -t checkmk-agent:test .
# The agent version is auto-detected from the server listing — no need to hardcode it.
ARG CMK_AGENT_URL=https://YOUR_CHECKMK_SERVER/monitoring/check_mk/agents

# Install dependencies
RUN microdnf install -y \
    python3 \
    socat \
    curl \
    procps-ng \
    shadow-utils \
    shadow-utils-subid \
    libseccomp \
    && microdnf clean all

# Wrap /usr/bin/env to inject PYTHONPATH so runagent sub-processes (runuser -l re-exec) find the agent module
RUN mv /usr/bin/env /usr/bin/env.orig && \
    printf '#!/bin/sh\nexec /usr/bin/env.orig PYTHONPATH=/usr/local/agent/pypkg "$@"\n' > /usr/bin/env && \
    chmod +x /usr/bin/env

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
