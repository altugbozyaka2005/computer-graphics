#!/bin/sh
# Runs every test (test1, test2, ...) and writes runAllTests.log; see README.txt.
#   ./runAllTests.sh [--renderer PATH] [--tests 1,2] [--outdir DIR] [--extra ARGS...]
exec python3 "$(dirname "$0")/runAllTests.py" "$@"
