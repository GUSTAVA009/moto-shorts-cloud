"""Make upstream Oracle ARM Qwen's installer safe for owner-private deployment.

Runs OFFLINE, modifies a copy in the user's VM, never touches upstream Git.
Upstream installs default Open Internet port 8000 and binds C engine to
INADDR_ANY: both are unacceptable for the owner-only HAPYCH Voice Studio.
"""
from __future__ import annotations

import argparse
from pathlib import Path


ENGINE_FRAGMENT = "git checkout feature/decoder-speed 2>/dev/null || true\nmake blas -j4"
INSECURE_FIREWALL = (
    "sudo iptables -I INPUT 5 -p tcp --dport 8000 -j ACCEPT || true",
    "sudo netfilter-persistent save 2>/dev/null || true",
)
UNSAFE_SERVICES = "sudo systemctl enable --now qwen_engine qwen_presets ttsserver"


def patch_vendor(root: Path):
    root = Path(root)
    install = root / "setup.sh"
    unit = root / "systemd" / "qwen_presets.service"
    setup_text = install.read_text(encoding="utf-8")
    service_text = unit.read_text(encoding="utf-8")

    if setup_text.count(ENGINE_FRAGMENT) != 1:
        raise ValueError("UPSTREAM_BUILD_SEQUENCE_CHANGED")
    if setup_text.count(UNSAFE_SERVICES) != 1:
        raise ValueError("UPSTREAM_SERVICES_CHANGED")
    if any(setup_text.count(x) != 1 for x in INSECURE_FIREWALL):
        raise ValueError("UPSTREAM_FIREWALL_CHANGED")
    if service_text.count("--int4 -j4") != 1:
        raise ValueError("UPSTREAM_PRESETS_SERVICE_CHANGED")

    # The C engine checks and patches only one exact INADDR_ANY socket bind
    # BEFORE compilation. If upstream changes, the build fails closed.
    python_patch = (
        "python3 - <<'HAPYCH_LOOPBACK_PATCH'\n"
        "from pathlib import Path\n"
        "f=Path('qwen_tts_server.c')\n"
        "s=f.read_text(encoding='utf-8')\n"
        "old='.sin_addr.s_addr = INADDR_ANY,'\n"
        "assert s.count(old)==1, 'QWEN_SOCKET_CHANGED_FAIL_CLOSED'\n"
        "f.write_text(s.replace(old,"
        "'.sin_addr.s_addr = htonl(INADDR_LOOPBACK),'),encoding='utf-8')\n"
        "HAPYCH_LOOPBACK_PATCH\n"
    )
    safe = setup_text.replace(
        ENGINE_FRAGMENT,
        "git checkout feature/decoder-speed 2>/dev/null || true\n"
        + python_patch + "make blas -j2",
    ).replace(
        UNSAFE_SERVICES,
        "sudo systemctl disable --now qwen_engine ttsserver || true\n"
        "sudo systemctl enable --now qwen_presets",
    )
    for command in INSECURE_FIREWALL:
        safe = safe.replace(command, "# HAPYCH REMOVED UNSAFE COMMAND: " + command)
    # Remove upstream's public-HTTP setup instructions; safe installation
    # MUST NOT invite an operator to open tcp/8000 for public access.
    safe = safe.replace(
        "echo \"NOTE: you must ALSO open TCP 8000 in the OCI console:\"",
        "echo \"HAPYCH: do NOT allow public tcp/8000, 8001 or 8002.\"",
    )
    safe = safe.replace(
        "echo \"  VCN -> Security Lists -> Default -> Add Ingress Rule (source 0.0.0.0/0, TCP 8000)\"",
        "echo \"HAPYCH: use HTTPS proxy to 127.0.0.1:8080 only.\"",
    )

    out = root / "setup-hapych-safe.sh"
    out.write_text(safe, encoding="utf-8")
    out.chmod(0o700)

    service_text = service_text.replace("OPENBLAS_NUM_THREADS=4",
                                        "OPENBLAS_NUM_THREADS=2")
    service_text = service_text.replace("--int4 -j4", "--int4 -j2")
    patched_unit = root / "systemd" / "qwen_presets.service"
    patched_unit.write_text(service_text, encoding="utf-8")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_dir", type=Path)
    args = parser.parse_args()
    print(patch_vendor(args.repo_dir))
