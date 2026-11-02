#!/usr/bin/env bash
# HAPYCH Factory: owner/operator-run, narrow Cartoon B production TTS activation.
# Run only on hapych-eu-de-01 as the VPS operator with sudo/root privileges.
# This script is NOT executed through SentinelX's restricted agent.
set -Eeuo pipefail
umask 077
if [ "$(id -u)" != "0" ]; then
  echo "OWNER_ACTION_REQUIRED: run with sudo on hapych-eu-de-01" >&2
  exit 2
fi

ROOT=/opt/hapych-factory-voice
TARGET="$ROOT/owner_clone_service.py"
POLICY=/etc/sentinelx/config.yaml
REF="$ROOT/private/owner_selected_20261102/CARTOON_TAKE2_B_MINUS2.wav"
MANIFEST="$ROOT/private/owner_selected_20261102/cartoon_voice_design_manifest.json"
SOURCE_COMMIT=7e2f622e953da5736a67b7b436492acde71bdd60
SOURCE_SHA=54b7a5cdf112632e783c86b90a701b67ea47a8e60f2b2130932d957913e93b6c
REF_SHA=76d834646534a0463889a824895a1e54ce5ed672b2dda46babba151b32a63aef
RUN_TAG=20261102
BASE="https://raw.githubusercontent.com/GUSTAVA009/moto-shorts-cloud/$SOURCE_COMMIT"
STAGE=$(mktemp -d /tmp/hapych-cartoon-b.XXXXXXXX)
CURRENT_CODE="$STAGE/current-tts-code.py"
CURRENT_POLICY="$STAGE/current-sentinelx-config.yaml"
OLD_CODE="$ROOT/owner_clone_service.py.before-cartoon-b-$RUN_TAG"
OLD_POLICY="$POLICY.before-cartoon-b-$RUN_TAG"
INSTALLED=0
COMPLETED=0

rollback() {
  code=$?
  trap - EXIT
  if [ "$COMPLETED" != "1" ]; then
    echo "DEPLOY_NOT_VERIFIED: restoring previous TTS code and policy" >&2
    if [ -f "$CURRENT_CODE" ] && [ "$INSTALLED" = "1" ]; then
      cp -p "$CURRENT_CODE" "$TARGET" || true
      systemctl restart hapych-factory-tts || true
    fi
    if [ -f "$CURRENT_POLICY" ]; then
      cp -p "$CURRENT_POLICY" "$POLICY" || true
      systemctl restart sentinelx-cloud-core || true
    fi
  fi
  rm -rf "$STAGE"
  exit "$code"
}
trap rollback EXIT

[ -s "$TARGET" ] && [ -s "$REF" ] && [ -s "$MANIFEST" ] &&
[ -s "$POLICY" ] && [ -x "$ROOT/venv/bin/python" ] || {
  echo "ACTIVATION_PREREQUISITES_MISSING" >&2
  exit 1
}

echo "Checking immutable upstream source and private owner's B reference..."
curl --fail --silent --show-error --location --max-time 35 --retry 2 \
  "$BASE/voice-studio/owner_clone_service.py" -o "$STAGE/owner_clone_service.py"

python3 - "$STAGE/owner_clone_service.py" "$REF" "$MANIFEST" "$SOURCE_SHA" "$REF_SHA" <<'PY'
import ast,hashlib,json,pathlib,sys
source,reference,manifest,expected_source,expected_ref = (
    pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]),
    pathlib.Path(sys.argv[3]),sys.argv[4],sys.argv[5])
raw=source.read_bytes()
ast.parse(raw.decode("utf8"))
assert hashlib.sha256(raw).hexdigest()==expected_source, "SOURCE_SHA_CHANGED"
assert b"CARTOON_B_VOICE_ID" in raw and b"gustava-cartoon-b-v1" in raw, "B_NOT_SUPPORTED"
assert hashlib.sha256(reference.read_bytes()).hexdigest()==expected_ref, "OWNER_B_WAV_CHANGED"
record=json.loads(manifest.read_text("utf8"))
selected=[r for r in record.get("candidates",[])
          if r.get("id")=="cartoon_original_voicedesign_v2_b"]
assert len(selected)==1 and selected[0].get("sha256_wav")==expected_ref, "OWNER_B_MANIFEST_CHANGED"
assert selected[0].get("asr_short_canary_passed") is True, "OWNER_B_SOURCE_QA_MISSING"
print("CARTOON_B_SHA_AND_PROVENANCE_VERIFIED")
PY

cp -p "$TARGET" "$CURRENT_CODE"
cp -p "$POLICY" "$CURRENT_POLICY"
if [ ! -e "$OLD_CODE" ]; then
  cp -p "$TARGET" "$OLD_CODE"
fi
if [ ! -e "$OLD_POLICY" ]; then
  cp -p "$POLICY" "$OLD_POLICY"
fi

# The OWNER is authorizing these narrowly scoped permissions in this
# operator-run command. Do not give the agent write access to the private
# voice/audio/credentials directories or to the SentinelX policy itself.
python3 - "$POLICY" <<'PY'
import os,pathlib,re,stat,sys,tempfile,yaml
path=pathlib.Path(sys.argv[1])
before=path.read_text("utf8")
data=yaml.safe_load(before)
if not isinstance(data,dict) or "services" not in data or "file_ops" not in data:
    raise SystemExit("UNRECOGNIZED_SENTINELX_POLICY")
if data.get("services",{}).get("hapych-factory-tts"):
    old=set(data["services"]["hapych-factory-tts"].get("actions",[]))
    if not {"status","restart"}.issubset(old):
        raise SystemExit("EXISTING_TTS_SERVICE_POLICY_REQUIRES_MANUAL_REVIEW")
if data.get("services",{}).get("hapych-factory-portal"):
    old=set(data["services"]["hapych-factory-portal"].get("actions",[]))
    if not {"status","restart"}.issubset(old):
        raise SystemExit("EXISTING_PORTAL_SERVICE_POLICY_REQUIRES_MANUAL_REVIEW")
text=before
entry=""
for name in ("hapych-factory-tts","hapych-factory-portal"):
    if not data["services"].get(name):
        entry += "  "+name+":\n    actions: [status, restart]\n"
if entry:
    if text.count("\nservices:\n")!=1:
        raise SystemExit("SERVICES_INSERTION_AMBIGUOUS")
    text=text.replace("\nservices:\n","\nservices:\n"+entry,1)
scope=""
paths=data["file_ops"].get("paths",[])
for name in ("owner_clone_service.py","live_portal.py"):
    owner_file="/opt/hapych-factory-voice/"+name
    existing=[x for x in paths if x.get("path")==owner_file]
    if existing and any(x.get("access")!="rw" for x in existing):
        raise SystemExit("EXISTING_FILE_POLICY_REQUIRES_MANUAL_REVIEW")
    if not existing:
        scope += "    - path: "+owner_file+"\n      access: rw\n"
if scope:
    if text.count("\nfile_ops:\n  paths:\n")!=1:
        raise SystemExit("FILE_OPS_INSERTION_AMBIGUOUS")
    text=text.replace("\nfile_ops:\n  paths:\n","\nfile_ops:\n  paths:\n"+scope,1)
updated=yaml.safe_load(text)
for name in ("hapych-factory-tts","hapych-factory-portal"):
    assert {"status","restart"}.issubset(set(updated["services"][name]["actions"]))
for name in ("owner_clone_service.py","live_portal.py"):
    assert any(row.get("path")=="/opt/hapych-factory-voice/"+name and row.get("access")=="rw"
               for row in updated["file_ops"]["paths"])
if text!=before:
    st=path.stat()
    fd,tmp=tempfile.mkstemp(prefix=".config.cartoon-b.",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp,stat.S_IMODE(st.st_mode))
        os.chown(tmp,st.st_uid,st.st_gid)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
print("OPERATOR_SCOPED_SENTINELX_POLICY_READY")
PY

install -o sentinelx -g sentinelx -m 0644 \
  "$STAGE/owner_clone_service.py" "$ROOT/owner_clone_service.py.cartoon-b.next"
"$ROOT/venv/bin/python" -m py_compile "$ROOT/owner_clone_service.py.cartoon-b.next"
mv -f "$ROOT/owner_clone_service.py.cartoon-b.next" "$TARGET"
INSTALLED=1

systemctl restart hapych-factory-tts

# Actual generation, not a fake readiness flag. The preexisting private
# owner key is read locally, never echoed, committed, or sent externally.
python3 - "$ROOT" "$REF_SHA" <<'PY'
from pathlib import Path
import hashlib,io,json,re,sys,time,urllib.request,wave
root=Path(sys.argv[1]);expected_ref=sys.argv[2]
ready=False
for _ in range(20):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8077/health",timeout=4) as r:
            state=json.load(r)
        if state.get("tts_ready_for_private_request") and state.get("cartoon_b_reference_ready"):
            ready=True
            break
    except Exception:
        pass
    time.sleep(0.5)
if not ready:
    raise SystemExit("LIVE_CARTOON_B_SERVER_NOT_READY")
keyfile=root/"private/owner-tts.env"
values={}
for line in keyfile.read_text("utf8").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k,v=line.split("=",1)
        values[k.strip()]=v.strip().strip("'\"")
key=values.get("OWNER_TTS_API_KEY","")
if not re.fullmatch(r"gvk_[A-Za-z0-9_-]{40,64}",key):
    raise SystemExit("OWNER_TTS_PRIVATE_AUTH_UNAVAILABLE")
payload={"voice":"gustava-cartoon-b-v1","channel_slug":"gustava",
         "response_format":"wav",
         "text":"Привет, байкеры! Мотор гудит. Я готов к поездке. Поехали, друзья!"}
data=json.dumps(payload,ensure_ascii=False).encode("utf8")
req=urllib.request.Request(
    "http://127.0.0.1:8077/v1/audio/speech",data=data,method="POST",
    headers={"Authorization":"Bearer "+key,"Content-Type":"application/json",
             "X-Idempotency-Key":"owner-cartoon-b-activation-20261102-v1"})
with urllib.request.urlopen(req,timeout=360) as response:
    assert response.status==200,"CARTOON_B_NOT_SYNTHESIZED"
    assert response.headers.get("X-Voice-ID")==payload["voice"],"VOICE_ID_MISMATCH"
    assert response.headers.get("X-Reference-SHA256")==expected_ref,"VOICE_REFERENCE_MISMATCH"
    assert response.headers.get("X-TTS-Backend")=="qwen3_0.6b_base_cartoon_b_reference"
    wav=response.read(12_000_001)
assert 10000<len(wav)<12_000_000, "EMPTY_OR_OVERSIZE_AUDIO"
with wave.open(io.BytesIO(wav),"rb") as w:
    assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(1,2,24000)
    duration=w.getnframes()/w.getframerate()
assert 3<=duration<=35, "WRONG_WAV_DURATION"
print("CARTOON_B_ACTUAL_WAV_GENERATED",
      "seconds",round(duration,2),"sha256",hashlib.sha256(wav).hexdigest())
PY

# Reload policy only after the new voice has produced a genuine valid WAV.
systemctl restart sentinelx-cloud-core
COMPLETED=1
echo "CARTOON_B_TTS_LIVE_AND_POLICY_INSTALLED"
echo "NEXT: GitHub Actions can now render SHA-pinned original Cartoon B episodes."
