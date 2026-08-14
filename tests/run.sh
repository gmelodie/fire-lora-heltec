#!/bin/bash
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"
# Build inside the repo: a noexec /tmp cannot run the binary it just built.
OUT=${TESTS_BUILD_DIR:-.build}
mkdir -p "$OUT"
g++ -std=c++17 -Wall -Wextra -I.. -o "$OUT/test_sensor_math" test_sensor_math.cpp
"$OUT/test_sensor_math"
