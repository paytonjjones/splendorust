#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 SEAL256_SOURCE_DIR OUTPUT" >&2
  exit 2
fi

source_dir=$1
output=$2
adapter_dir=$(cd "$(dirname "$0")/../adapters" && pwd)

clang++ -O3 -DNDEBUG -std=c++20 -pthread \
  -I"$source_dir/src" \
  "$source_dir/src/splendor.cpp" \
  "$source_dir/src/game_state.cpp" \
  "$source_dir/src/mcts.cpp" \
  "$source_dir/src/agents.cpp" \
  "$source_dir/src/random_util.cpp" \
  "$adapter_dir/seal256_strength.cpp" \
  -o "$output"
