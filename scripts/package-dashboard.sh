#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT/dashboard"
if [ ! -d node_modules ]; then npm ci; else npm install --prefer-offline --no-audit --no-fund; fi
npm run build
rm -rf "$ROOT/backend/static_dash"
cp -R dist "$ROOT/backend/static_dash"
