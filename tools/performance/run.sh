#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
variant=${1:?Usage: run.sh before|after}
for profile in desktop phone1g tablet1g phone2g tablet2g veryweak; do
  memory=1g
  if [[ "$profile" == desktop || "$profile" == phone2g || "$profile" == tablet2g ]]; then memory=2g; fi
  if [[ "$profile" == veryweak ]]; then memory=512m; fi
  docker run --rm --init --memory="$memory" --memory-swap="$memory" --cpus=1 --shm-size=128m \
    --network=sibforum-audit_default -e NODE_PATH=/audit/node_modules \
    -v "$PWD/tools/performance:/tests:ro" -v "$PWD/docs/performance-results:/results" \
    sibforum-perf-runner:1.63.0 node /tests/measure.cjs "$variant" "$profile" "/results/$variant-$profile.json"
done
