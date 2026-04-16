# ns8-checkmk-agent

Containerized CheckMK agent for NethServer 8 (NS8).

Runs the official `check-mk-agent` RPM inside a Rocky Linux 9 container, exposes port 6556,
and supports deep NS8 module checks via `runagent` (including rootless Podman container inspection).

## Features

- CheckMK agent auto-installed from the configured monitoring server (version auto-detected)
- Built-in system checks work out of the box (CPU, memory, disk, network, processes)
- SOS session check included (`check-sos`)
- `runagent` fully functional from inside the container: can inspect rootless module containers
  (webtop, mail, nethvoice, samba, etc.) without installing anything on the host
- No native RPM or systemd unit needed on the NS8 host

## Build

```bash
podman build -t checkmk-agent:latest .
```

Override the CheckMK server URL if needed:

```bash
podman build \
  --build-arg CMK_AGENT_URL=https://<your-checkmk-server>/<site>/check_mk/agents \
  -t checkmk-agent:latest .
```

## Deploy

The container needs several bind mounts from the NS8 host to support `runagent`
and NS8 module checks. All mounts are read-only except `/run/user`.

### Minimal deployment (system checks + SOS only)

```bash
podman run -d \
  --name checkmk-agent \
  --restart=always \
  --privileged \
  --pid=host \
  -p 6556:6556 \
  --security-opt label=disable \
  checkmk-agent:latest
```

### Full NS8 deployment (with runagent + module checks)

```bash
podman run -d \
  --name checkmk-agent \
  --restart=always \
  --privileged \
  --pid=host \
  --cgroupns=host \
  -p 6556:6556 \
  -v /usr/local/agent:/usr/local/agent:ro \
  -v /usr/local/bin/runagent:/usr/local/bin/runagent:ro \
  -v /usr/bin/python3.11:/usr/bin/python3.11:ro \
  -v /usr/bin/podman:/usr/bin/podman:ro \
  -v /usr/lib64/libpython3.11.so.1.0:/usr/lib64/libpython3.11.so.1.0:ro \
  -v /usr/lib64/python3.11:/usr/lib64/python3.11:ro \
  -v /etc/passwd:/etc/passwd:ro \
  -v /etc/group:/etc/group:ro \
  -v /etc/shadow:/etc/shadow:ro \
  -v /etc/nethserver:/etc/nethserver:ro \
  -v /run/user:/run/user \
  -v /home:/home:ro \
  --security-opt label=disable \
  checkmk-agent:latest
```

### Mount reference

| Flag / Mount | Purpose |
|---|---|
| `--cgroupns=host` | Share host cgroup namespace — required for `podman exec` into rootless module containers |
| `/usr/local/agent` | NS8 agent Python environment (runagent runtime) |
| `/usr/local/bin/runagent` | NS8 runagent binary |
| `/usr/bin/python3.11` | Python 3.11 binary (required by runagent shebang) |
| `/usr/bin/podman` | Podman binary (for module container inspection) |
| `/usr/lib64/libpython3.11.so.1.0` | Python 3.11 shared library |
| `/usr/lib64/python3.11` | Python 3.11 standard library |
| `/etc/passwd`, `/etc/group`, `/etc/shadow` | Host user/group database (module users) |
| `/etc/nethserver` | NS8 agent configuration (agent.env) |
| `/run/user` | Module user runtime dirs (XDG_RUNTIME_DIR, Podman storage) |
| `/home` | Module user home dirs (agent state, environment files) |

## How runagent works from the container

NS8 module containers (webtop, mail, nethvoice, etc.) run as rootless Podman under
dedicated Linux users (e.g. `webtop3` with UID 1015). The `runagent` tool switches
context to those users via `runuser -l` to run commands in their environment.

The container's `/usr/bin/env` is wrapped to inject `PYTHONPATH=/usr/local/agent/pypkg`
into the `runuser` sub-process environment (since `runuser -l` resets all env vars).
This allows the second `runagent` invocation (running as the module user) to find the
NS8 `agent` Python module. `PYTHONPATH` is also set via `ENV` in the image for the
initial invocation.

**`--cgroupns=host` is required** for `podman exec` into rootless module containers.
Without it, the container uses a private cgroup namespace and cannot see the cgroup
paths of `user.slice/user-<uid>.slice/...` where module containers live. This causes
`podman exec` to fail with `crun: write to /sys/fs/cgroup/.../cgroup.procs: No such file or directory`.

Example - list webtop3 containers from inside the running container:

```bash
podman exec checkmk-agent runagent -m webtop3 podman ps
```

## Local checks

Custom check scripts in `checks/` are copied into `/usr/lib/check_mk_agent/local/`
at build time. Currently deployed:

| Script | Service name | Description |
|---|---|---|
| `check-sos` | `SOS.Session` | Checks whether an active SOS support session is running |

Additional NS8-aware check scripts are in `checks-rootless/` and use `runagent`
to inspect module containers. They are deployed by `Dockerfile.runagent` (Full NS8 build).
To include them in the minimal build, copy selected scripts into `checks/`.

## Stopping and removing

```bash
podman stop checkmk-agent
podman rm checkmk-agent
```

## Verify agent output

```bash
podman exec checkmk-agent check_mk_agent | head -20
```
