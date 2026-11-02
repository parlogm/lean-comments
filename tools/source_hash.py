#!/usr/bin/env python3
"""usage: source_hash.py [--write | --check]: tracks whether bin/ was built from the current hook sources."""
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ["hook/Cargo.toml", "hook/Cargo.lock", "hook/.cargo/config.toml", "hook/src/main.rs", "hooks/comment-rule.md"]
BUILDS = ["macos-arm64", "macos-x86_64", "linux-x86_64", "linux-arm64", "windows-x86_64.exe"]
RECORD = ROOT / "bin/SOURCE_HASH"


def current():
    digest = hashlib.sha256()
    for name in SOURCES:
        digest.update(name.encode() + b"\0" + (ROOT / name).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


if "--write" in sys.argv:
    RECORD.write_text(current() + "\n")
elif "--check" in sys.argv:
    complete = all((ROOT / f"bin/lean-comments-{build}").exists() for build in BUILDS)
    if not complete or not RECORD.exists() or RECORD.read_text().strip() != current():
        sys.exit("bin/ is stale: push a commit with [build binaries] in its message to rebuild and commit it.")
else:
    print(current())
