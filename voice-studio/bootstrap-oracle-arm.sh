#!/usr/bin/env bash
# HAPYCH Qwen3 CPU bootstrap for OWNER'S ORACLE CLOUD ARM64 VM ONLY.
# Does not provision cloud instances, request cards, open ports or incur bills.
set -euo pipefail
if [ "$(uname -m)" != "aarch64" ]; then
  echo "FAIL_CLOSED: requires an Oracle aarch64 Linux VM, not user's computer." >&2
  exit 2
fi
if [ "$(id -u)" -eq 0 ]; then
  echo "Run as the VM's ordinary account with sudo; not root." >&2
  exit 2
fi
if [ ! -f ./compose.yaml ] || [ ! -f ./patch_vendor_cpu.py ]; then
  echo "Run inside the voice-studio directory of the GUSTAVA repo." >&2
  exit 2
fi
ROOT="$(pwd)"
if [ -e ./.env ]; then
  echo "Existing private .env preserved unchanged."
else
  echo "Create .env from .env.example and add TWO different strong secrets."
fi
command -v git >/dev/null || {
  echo "Install git on the cloud VM first: sudo apt-get install -y git" >&2
  exit 2
}
WORKDIR="$HOME/hapych-qwen3-free-cpu"
if [ ! -d "$WORKDIR/.git" ]; then
  git clone https://github.com/TrinityTF/qwen3-tts-server.git "$WORKDIR"
fi
# Validate exact upstream installer and make an owner-private safe copy.
# Upstream setup.sh enables a PUBLIC port by default; never execute it.
python3 "$ROOT/patch_vendor_cpu.py" "$WORKDIR"
bash "$WORKDIR/setup-hapych-safe.sh"
# The C voice presets server must be accessible ONLY through loopback.
if sudo ss -lntp | grep -E ':800(0|1|2)\b' | grep -v '127.0.0.1:8002' | grep -v '\[::ffff:127.0.0.1\]:8002'; then
  echo "FAIL_CLOSED: unexpected public TTS port; do not publish." >&2
  exit 3
fi
if ! curl --silent --fail --max-time 15 \
      http://127.0.0.1:8002/v1/speakers >/dev/null; then
  echo "CPU engine unavailable. Check sudo journalctl -u qwen_presets." >&2
  exit 4
fi
echo "CPU_CLOUD_READY: private Qwen engine at 127.0.0.1:8002."
echo "Next: docker compose up -d --build and enable HTTPS owner-only proxy."
