# Live free TTS for GUSTAVA Factory — Qwen 0.6B cloned Deep

## Status and constraints
This service is a private self-hosted inference engine. Model runtime
and the voice reference are on a server; GitHub Actions only sends a signed
short-lived owner identity token. **A working WAV is not a published YouTube
Short and a cloned timbre is not considered approved without listening/ASR.**

The host is `hapych-eu-de-01`, and the working directory is
`/opt/hapych-factory-voice`. It does **not** use or access user-local video
files. The server also hosts important HAPYCH VPN services, therefore it
runs as an isolated, non-root service and is protected by systemd
`CPUQuota`, `MemoryMax` and `NoNewPrivileges`. Never reconfigure the
existing VPN tunnel. Use an independent named Cloudflare tunnel.

The upstream C engine commit pinned during initial deployment:
`ef339be58a778b062e1c14382347964552eae007`, MIT source, Qwen
official Apache 2.0 model `Qwen3-TTS-12Hz-0.6B-Base`. Use only the approved
voice reference for GUSTAVA (real SHA-256 below), never random speaker presets.

## Verified preliminary proof (not yet editorially approved)
- 0.6B Base weights: downloaded into private host, 2.4 GiB directory.
- CPU compiled using `make blas -j2` on AMD EPYC 9454 vCPU with
  AVX-512/VNNI.
- Three historical provider Deep preview MP3 bytes matched original
  per-episode SHA-256 before joining.
- Private 30.528s PCM16 mono reference WAV:
  `ed27b23b9f86345c45263ab28957e96fd2d399379b3ea90ed9fbc75be183a3cc`.
- Real private Russian speech generated: 7.68s WAV in 9.9s of compute,
  RTF 1.29. **Not a claim that the cloned voice matches historical Deep.**

## Production endpoint
`https://voice.hapychrust.ru/v1/audio/speech` only. The service
`owner_clone_service.py` is bound to `127.0.0.1:8077`; Cloudflare's
named tunnel provides HTTPS (never open 8077 in public firewall).
Source files and API keys are readable only by the isolated service user.

### GitHub Actions without a private API key
GitHub workflows declare `permissions: id-token: write`. Only the
official owner repository ID `1436068497`, `refs/heads/main`, the
trusted `daily-preview.yml` or `render-new-short.yml` workflows, issuer
`https://token.actions.githubusercontent.com` and audience
`voice.hapychrust.ru` are allowed by server signature and claim checks.
No ID token or owner API key is written to logs, code, or artifacts.
Production route uses `GUSTAVA_VOICE_OIDC_ENABLED=1`; when this is
explicitly disabled, it fails closed unless an existing private
`GUSTAVA_VOICE_API_KEY` is configured.

### Request and response
POST JSON:
`{"text":"...","voice":"gustava-original-v1","channel_slug":"gustava","response_format":"wav"}`
with `Authorization: Bearer <OIDC or owner gvk>` and unique
`X-Idempotency-Key`. Response must include
`X-Voice-ID`, `X-Channel-ID`, `X-Reference-SHA256`,
`X-Audio-SHA256` and actual, non-silent WAV.
Idempotency collisions or a reference SHA mismatch block production.

## Go/no-go for public release
1. DNS and independent Cloudflare tunnel online with the correct
   response over HTTPS.
2. Genuine GitHub Actions OIDC request accepted; a fork token rejected.
3. A real, unique original episode has new rights-proven footage,
   narrated with real model audio; source and mixed ASR both pass.
4. Correct Russian speech, continuity and actual Deep timbre review
   approved. Never silently use Silero, Kokoro or unrelated preset.
5. MP4/thumbnail/story and owner editorial checks pass.
6. Only then enable `auto_publish` for that episode and inspect
   Buffer Post ID, Buffer sent and independent public YouTube URL.

The target 400/month remains a capacity objective, **not verified
monthly production** until all the above hold repeatedly. Low original
footage stock is a separate blocker; opening TTS does not clear it.
