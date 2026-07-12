#!/usr/bin/env bash
# Deploy the docs site to the docs host (docs.vpn-hub.pro).
# Usage: ./scripts/deploy-docs.sh <user@host>
set -euo pipefail

HOST="${1:?Usage: $0 <user@host>}"

npm run build --prefix docs-site
rsync -az --delete --timeout=30 docs-site/.vitepress/dist/ "$HOST:/opt/vpnhub-docs/"
curl -s -o /dev/null -w 'docs: %{http_code}\n' https://docs.vpn-hub.pro/
