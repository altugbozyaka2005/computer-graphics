#!/bin/sh
# Runs test 27 only (renderer: ../../output/CGR26_renderer unless --renderer is given).
cd "$(dirname "$0")/.." && exec python3 runAllTests.py --tests 27 "$@"
