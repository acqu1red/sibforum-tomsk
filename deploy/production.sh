#!/usr/bin/env bash
set -euo pipefail

action=${1:-check}
env_file=${2:-/etc/sibforum/production.env}
project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"

if [[ ! -f "$env_file" ]]; then
  echo "Environment file not found: $env_file" >&2
  exit 1
fi
compose=(docker compose --env-file "$env_file" -f docker-compose.prod.yml)
bootstrap=("${compose[@]}" -f docker-compose.bootstrap.yml)
"${compose[@]}" config --quiet
# Validate the rendered configuration without printing its secrets.
"${compose[@]}" config --format json | python3 -c '
import json, sys
c = json.load(sys.stdin)
n = c["services"]["nginx"]["environment"]
if str(n.get("PUBLIC_SUBMISSIONS_ENABLED", "0")) == "1":
    e = c["services"]["backend-prod"]["environment"]
    needed = ["DEFAULT_FROM_EMAIL", "YANDEX_SMARTCAPTCHA_SECRET", "YANDEX_SMARTCAPTCHA_CLIENT_ID"]
    if e.get("EMAIL_BACKEND") == "config.postbox.EmailBackend":
        needed += ["POSTBOX_ACCESS_KEY_ID", "POSTBOX_SECRET_ACCESS_KEY"]
    else:
        needed += ["EMAIL_HOST"]
    missing = [name for name in needed if not e.get(name)]
    if missing:
        sys.exit("Cannot open public submissions; missing: " + ", ".join(missing))
'

case "$action" in
  check)
    "${compose[@]}" run --rm --no-deps backend-prod python manage.py check --deploy --fail-level WARNING
    ;;
  bootstrap)
    # Only use before the first certificate has been issued.
    "${bootstrap[@]}" up -d --build --wait db backend-prod nginx
    ;;
  https)
    # The bootstrap nginx must already be serving the ACME webroot on port 80.
    "${compose[@]}" run --rm --no-deps certbot
    "${compose[@]}" up -d --wait
    "${compose[@]}" exec -T nginx nginx -t
    ;;
  update)
    # Reject template errors before touching the running backend or proxy.
    "${compose[@]}" run --rm --no-deps nginx sh /etc/nginx/project/check-nginx.sh
    "${compose[@]}" build
    "${compose[@]}" exec -T backend-prod python manage.py backup_data
    "${compose[@]}" stop worker backup
    "${compose[@]}" up -d --wait
    # Render changed templates and resolve the current upstream address.
    "${compose[@]}" up -d --no-deps --force-recreate --wait nginx
    "${compose[@]}" exec -T nginx nginx -t
    ;;
  renew)
    "${compose[@]}" run --rm --no-deps certbot renew --quiet
    "${compose[@]}" exec -T nginx nginx -t
    "${compose[@]}" exec -T nginx nginx -s reload
    ;;
  *)
    echo "Usage: $0 {check|bootstrap|https|update|renew} [/path/to/production.env]" >&2
    exit 2
    ;;
esac
