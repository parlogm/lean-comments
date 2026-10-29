#!/usr/bin/env bash
# Commits the pre-change ConfigMerger, then lays the essay-commented uncommitted version on top.
set -eu
here="$(dirname "$0")"
cp -R "$here/files/." .
f=src/main/java/com/acme/config/ConfigMerger.java
noisy="$(cat "$f")"
cp .base/ConfigMerger.java "$f"
rm -rf .base
git init -q && git add -A && git -c user.email=eval@example.com -c user.name=eval commit -qm "config merger"
printf '%s\n' "$noisy" > "$f"
