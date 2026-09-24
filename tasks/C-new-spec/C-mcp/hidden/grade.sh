#!/bin/sh
# Grade an implementation of task C-mcp offline. Usage: grade.sh <repo_dir> [--out DIR]
# Prints one JSON object (see grade.py). Proxy variables are cleared inside grade.py.
exec python3 "$(dirname "$0")/grade.py" "$@"
