#!/usr/bin/env bash
set -euo pipefail

target=${1:?Usage: upload.sh user@server [ssh-key]}
ssh_key=${2:-$HOME/.ssh/id_ed25519_sibforum_timeweb}
if [[ ! "$target" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*@[a-zA-Z0-9.-]+$ ]]; then
  echo 'Expected user@hostname or user@IPv4' >&2
  exit 2
fi
project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"
node tools/performance/render-home.cjs
node tools/performance/version-assets.cjs
ssh_options=(-i "$ssh_key" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new)
ssh "${ssh_options[@]}" "$target" 'install -d -m 755 /opt/sibforum'
# Explicit source list: never transmit local databases, browser profiles or SSH keys.
COPYFILE_DISABLE=1 tar --no-xattrs \
  --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='*.sqlite3*' --exclude='.chrome*' --exclude='.review-*' \
  --exclude='staticfiles' --exclude='media' --exclude='backups' \
  --exclude='.env*' --exclude='*.pem' --exclude='*.key' --exclude='.DS_Store' \
  -czf - backend site deploy docker-compose.prod.yml docker-compose.bootstrap.yml \
  | ssh "${ssh_options[@]}" "$target" 'tar -xzf - -C /opt/sibforum'
echo 'Sources uploaded to /opt/sibforum. Production secrets and data were not changed.'
