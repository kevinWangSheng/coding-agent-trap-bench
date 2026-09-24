#!/bin/sh
# usage: grade.sh <candidate_repo> [--out result.json] [--keep] [--reps N] [--skip-tests]
# Prints the grading JSON on stdout (progress on stderr). See grade.py for details.
exec python3 "$(dirname "$0")/grade.py" "$@"
