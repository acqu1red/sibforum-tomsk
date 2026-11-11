#!/bin/sh
set -eu

# Check the same rendered template as the live service, without replacing it.
envsubst '$DOMAIN $ADMIN_DOMAIN $PUBLIC_SUBMISSIONS_ENABLED $PUBLIC_VOTING_ENABLED $PUBLIC_ASSET_BASE_URL' \
  < "/etc/nginx/project/$NGINX_TEMPLATE" > /etc/nginx/conf.d/default.conf
exec nginx -t
