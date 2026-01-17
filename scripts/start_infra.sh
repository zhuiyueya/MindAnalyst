#!/bin/bash
set -e

# Get the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$DIR/.."

echo "Starting infrastructure..."
docker-compose -f "$PROJECT_ROOT/docker-compose.yml" up -d

echo "Waiting for services to be ready..."
# Simple wait loop
sleep 5

echo "Infrastructure is up!"
