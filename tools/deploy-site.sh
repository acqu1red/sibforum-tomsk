#!/usr/bin/env bash
set -euo pipefail
output_dir=${1:?Pass a staging directory}
node tools/performance/publish-forum.cjs
node tools/performance/version-assets.cjs
node tools/build-site.cjs "$output_dir"
SITE_BUILD_DIR="$output_dir" node tools/performance/version-assets.cjs
