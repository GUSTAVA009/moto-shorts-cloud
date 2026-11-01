#!/usr/bin/env bash
# For OWNER'S ORACLE CLOUD FREE ARM VM ONLY, Ubuntu 22.04/24.04, aarch64.
# No local PC, no NVIDIA GPU, no metered third-party voice API.
# Prerequisites: Oracle account/VM already provisioned by the owner.
# This script does NOT create paid Oracle resources or change DNS/firewall.
set -euo pipefail

if [ "$(uname -m)" != "aarch64" ]; then
  echo "FAIL_CLOSED: this bootstrap is for an ARM64 Oracle Cloud VM, not your PC." >&2
  exit 2
fi
if [ "$(id -u)" -eq 0 ]; then
  echo "FAIL_CLOSED: execute as your normal VM user with sudo, not root." >&2
  exit 2
fi
if [ ! -f ./compose.yaml ] || [ ! -f ./.env.example ]; then
  echo "Run from the repository's voice-studio directory." >&2
  exit 2
fi
if [ -e ./.env ]; then
  echo "Existing .env preserved. Do not overwrite owner credentials." >&2
else
  echo "No .env found. Create private admin+session secrets before Docker start." >&2
fi

# The upstream CPU project is independently licensed and implements the
# actual /v1/tts endpoint. Do not blindly expose its default public ports.
WORKDIR="$HOME/hapych-qwen3-free-cpu"
if [ ! -d "$WORKDIR/.git" ]; then
  git clone https://github.com/TrinityTF/qwen3-tts-server.git "$WORKDIR"
fi
cd "$WORKDIR"
python3 - <<'PY'
from pathlib import Path
p=Path("setup.sh")
s=p.read_text(encoding="utf-8")
old="git checkout feature/decoder-speed 2>/dev/null || true\nmake blas -j4"
new=('git checkout feature/decoder-speed 2>/dev/null || true\n'
     '# HAPYCH SECURITY PATCH: C engine binds 127.0.0.1 instead of 0.0.0.0.\n'
     'python3 - <<\\'HAPYCH_PATCH\\'\n'
     'from pathlib import Path\n'
     'f=Path("qwen_tts_server.c")\n'
     's=f.read_text()\n'
     'old=".sin_addr.s_addr = INADDR_ANY,"\n'
     'assert s.count(old)==1, "Upstream socket binding changed: refuse insecure boot"\n'
     'f.write_text(s.replace(old,".sin_addr.s_addr = htonl(INADDR_LOOPBACK),"))\n'
     'HAPYCH_PATCH\n'
     'make blas -j2')
if old not in s and new not in s:
    raise SystemExit("Upstream bootstrap changed; inspect before any installation")
if old in s:
    s=s.replace(old,new)
for unsafe in (
    "sudo iptables -I INPUT 5 -p tcp --dport 8000 -j ACCEPT || true",
    "sudo netfilter-persistent save 2>/dev/null || true",
):
    if unsafe not in s and "# HAPYCH REMOVED "+unsafe not in s:
        raise SystemExit("Upstream firewall script changed; inspect first")
    s=s.replace(unsafe,"# HAPYCH REMOVED "+unsafe)
s=s.replace("sudo systemctl enable --now qwen_engine qwen_presets ttsserver",
            "sudo systemctl disable --now qwen_engine ttsserver || true\n"
            "sudo systemctl enable --now qwen_presets")
# Never open the upstream's public UI or CPU engine to the internet.
p.write_text(s,encoding="utf-8")
unit=Path("systemd/qwen_presets.service")
u=unit.read_text(encoding="utf-8")
u=u.replace("OPENBLAS_NUM_THREADS=4","OPENBLAS_NUM_THREADS=2")
u=u.replace("--int4 -j4","--int4 -j2")
unit.write_text(u,encoding="utf-8")
print("Verified safe localhost-only CPU build script; vendor public port disabled.")
PY
bash ./setup.sh

# Independently prove the modified engine binds loopback only.
if sudo ss -lntp | grep -E ':800(0|1|2)\b' | grep -v '127.0.0.1:8002' | grep -v '\[::ffff:127.0.0.1\]:8002'; then
  echo "FAIL_CLOSED: a vendor service exposes CPU port beyond loopback." >&2
  exit 3
fi
if ! curl --silent --fail --max-time 15 http://127.0.0.1:8002/v1/speakers >/dev/null; then
  echo "CPU engine did not start. Inspect sudo journalctl -u qwen_presets." >&2
  exit 4
fi
echo "SAFE_CPU_ENGINE_UP: 127.0.0.1:8002; no GPU/PC required."
echo "Next: install Docker Engine/Compose on VM, configure private voice-studio/.env,"
echo "then docker compose up -d --build; use HTTPS proxy + private owner access."
