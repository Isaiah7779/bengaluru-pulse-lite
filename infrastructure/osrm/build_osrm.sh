#!/usr/bin/env bash
# Build an OSRM MLD graph for one profile. Usage: build_osrm.sh <profile> <dir>
set -euo pipefail
prof="$1"; dir="$2"
img=ghcr.io/project-osrm/osrm-backend:latest
export MSYS_NO_PATHCONV=1
docker run --rm -v "$dir:/data" $img osrm-extract -p /opt/$prof.lua /data/bengaluru.osm.pbf
docker run --rm -v "$dir:/data" $img osrm-partition /data/bengaluru.osrm
docker run --rm -v "$dir:/data" $img osrm-customize /data/bengaluru.osrm
echo "DONE $prof"
