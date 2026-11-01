#!/usr/bin/env bash
# Ubuntu 22.04/24.04 ARM64 on an owner-provisioned Always Free OCI A1 VM.
# No GPU, no owner's PC, no paid TTS provider, no external TTS token.
set -euo pipefail
if [ "$(id -u)" = 0 ] || [ "$(uname -m)" != "aarch64" ]; then
 echo "Run as non-root sudo user on an ARM64 cloud VM." >&2; exit 1
fi
SRC="$(cd "$(dirname "$0")" && pwd)"
ENGINE=/opt/hapych/qwen-engine
MODEL=/opt/hapych/model
APP=/opt/hapych/voice-studio
DATA=/var/lib/hapych-voice
test -f "$SRC/app.py" || { echo 'Voice Studio source missing' >&2; exit 1; }
echo '[1/5] Install free CPU libraries.'
sudo apt-get update
sudo apt-get install -y git ffmpeg curl build-essential cmake python3-venv libopenblas-dev libgomp1 ca-certificates

echo '[2/5] Build Qwen3-TTS optimized ARM C inference (2 threads).'
sudo mkdir -p /opt/hapych
sudo chown "$USER":"$USER" /opt/hapych
if [ ! -d "$ENGINE/.git" ]; then
 git clone --depth 1 https://github.com/TrinityTF/qwen3-tts.git "$ENGINE"
fi
(cd "$ENGINE" && make blas -j2)
test -x "$ENGINE/qwen_tts"

echo '[3/5] Install website and official open-weight CustomVoice model.'
sudo mkdir -p "$MODEL" "$APP" "$DATA"
sudo chown "$USER":"$USER" "$MODEL" "$APP" "$DATA"
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --no-cache-dir -r "$SRC/requirements.txt" "huggingface_hub[cli]>=0.30,<2"
if [ ! -s "$MODEL/model.safetensors" ]; then
 "$APP/venv/bin/hf" download Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice --local-dir "$MODEL"
fi
test -s "$MODEL/model.safetensors"
sudo cp "$SRC/app.py" "$SRC/core.py" "$SRC/index.html" "$SRC/site.css" "$SRC/site.js" "$SRC/login.html" "$SRC/login.css" "$SRC/login.js" "$APP/"
if ! id hapych-voice >/dev/null 2>&1; then
 sudo useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin hapych-voice
fi
sudo chown -R hapych-voice:hapych-voice "$APP" "$DATA"
sudo chown -R hapych-voice:hapych-voice "$MODEL"
sudo chown -R hapych-voice:hapych-voice "$ENGINE"

echo '[4/5] Create two independent private credentials if absent.'
sudo mkdir -p /etc/hapych
if [ ! -s /etc/hapych/voice.env ]; then
 ADMIN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
 SESSION="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
 sudo tee /etc/hapych/voice.env >/dev/null <<EOF
VOICE_STUDIO_ADMIN_TOKEN=$ADMIN
VOICE_STUDIO_SESSION_SECRET=$SESSION
VOICE_STUDIO_DATA=$DATA
QWEN_BACKEND_URL=http://127.0.0.1:8002
VOICE_STUDIO_LOCAL_HTTP=0
EOF
 unset ADMIN SESSION
fi
sudo chown root:hapych-voice /etc/hapych/voice.env
sudo chmod 0640 /etc/hapych/voice.env

echo '[5/5] Enable private cloud services with crash recovery.'
sudo tee /etc/systemd/system/hapych-qwen-cpu.service >/dev/null <<EOF
[Unit]
Description=HAPYCH Qwen3 CPU CustomVoice C engine
After=network.target
[Service]
User=hapych-voice
Group=hapych-voice
WorkingDirectory=$ENGINE
Environment=OPENBLAS_NUM_THREADS=2
Environment=QWEN_SD_INT8=1
ExecStart=$ENGINE/qwen_tts -d $MODEL --serve 8002 --int4 -j2 --silent
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
PrivateTmp=true
IPAddressDeny=any
IPAddressAllow=localhost
[Install]
WantedBy=multi-user.target
EOF
sudo tee /etc/systemd/system/hapych-voice-api.service >/dev/null <<EOF
[Unit]
Description=HAPYCH owner-only multi-channel voice API
Requires=hapych-qwen-cpu.service
After=network.target hapych-qwen-cpu.service
[Service]
User=hapych-voice
Group=hapych-voice
WorkingDirectory=$APP
EnvironmentFile=/etc/hapych/voice.env
ExecStart=$APP/venv/bin/uvicorn app:app --host 127.0.0.1 --port 8080 --workers 1 --no-server-header
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=$DATA
PrivateTmp=true
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now hapych-qwen-cpu.service hapych-voice-api.service
echo 'Web admin and Qwen engine are LOOPBACK-ONLY. Public DNS / HTTPS NOT configured.'
echo 'Owner login secret: sudo cat /etc/hapych/voice.env (never share it).'
echo 'Verify free cloud CPU Russian speech in studio before claiming production ready.'
