#!/usr/bin/env bash
# Build the three Bengaluru OSRM graphs (car, foot, bicycle) from OpenStreetMap.
#
#   infrastructure/osrm/prepare_graphs.sh [DATA_DIR]
#
# 1. downloads Geofabrik's India "Southern Zone" extract (~560 MB, ODbL),
# 2. cuts the Bengaluru metropolitan box (lon 77.00-78.00, lat 12.45-13.42;
#    measured from the extract used during development) with osmium-tool,
# 3. runs osrm-extract/partition/customize (MLD) once per profile.
#
# Graphs are written once and mounted read-only by docker-compose; restarting
# the stack never rebuilds them. Peak RAM per build measured at ~0.6 GB.
set -euo pipefail

DATA="${1:-$(pwd)/data}"
BBOX="77.00,12.45,78.00,13.42"
SRC_URL="https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf"
OSRM_IMAGE="ghcr.io/project-osrm/osrm-backend:latest"
export MSYS_NO_PATHCONV=1

mkdir -p "$DATA/osm" "$DATA/osrm-foot" "$DATA/osrm-bicycle"

if [ ! -f "$DATA/osm/southern-zone-latest.osm.pbf" ]; then
  echo "Downloading $SRC_URL"
  curl -fL --retry 3 -o "$DATA/osm/southern-zone-latest.osm.pbf" "$SRC_URL"
fi

echo "Extracting Bengaluru box $BBOX"
docker run --rm -v "$DATA/osm:/data" debian:bookworm-slim sh -c \
  "apt-get update -qq && apt-get install -y -qq osmium-tool >/dev/null && \
   osmium extract -b $BBOX --strategy complete_ways --overwrite \
     -o /data/bengaluru.osm.pbf /data/southern-zone-latest.osm.pbf"

cp "$DATA/osm/bengaluru.osm.pbf" "$DATA/osrm-foot/bengaluru.osm.pbf"
cp "$DATA/osm/bengaluru.osm.pbf" "$DATA/osrm-bicycle/bengaluru.osm.pbf"

build() { # profile dir
  docker run --rm -v "$2:/data" "$OSRM_IMAGE" osrm-extract -p "/opt/$1.lua" /data/bengaluru.osm.pbf
  docker run --rm -v "$2:/data" "$OSRM_IMAGE" osrm-partition /data/bengaluru.osrm
  docker run --rm -v "$2:/data" "$OSRM_IMAGE" osrm-customize /data/bengaluru.osrm
}
build car "$DATA/osm"
build foot "$DATA/osrm-foot"
build bicycle "$DATA/osrm-bicycle"
echo "Graphs ready in $DATA/osm, $DATA/osrm-foot, $DATA/osrm-bicycle"
