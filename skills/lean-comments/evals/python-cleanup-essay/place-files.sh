#!/usr/bin/env bash
# Commits the pre-change module, then lays the over-commented uncommitted version on top.
set -eu
here="$(dirname "$0")"
cp -R "$here/files/." .
noisy="$(cat billing/proration.py)"
cp .base/proration.py billing/proration.py
rm -rf .base
git init -q && git add -A && git -c user.email=eval@example.com -c user.name=eval commit -qm "billing"
printf '%s\n' "$noisy" > billing/proration.py
