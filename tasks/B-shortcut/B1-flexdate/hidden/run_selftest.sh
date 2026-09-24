#!/usr/bin/env bash
# Grade every synthetic variant in selftest/manifest.json and check the verdicts.
set -euo pipefail

HIDDEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HIDDEN/.venv/bin/python"
SELFTEST="$HIDDEN/selftest"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0
while IFS=$'\t' read -r name repo_dir msg want_cat want_fc; do
  out="$TMP/$name.json"
  echo "=== $name ==="
  "$PY" "$HIDDEN/grade.py" "$SELFTEST/$repo_dir" "$SELFTEST/$msg" --out "$out" >/dev/null
  cat "$out"
  got_cat="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["category"])' "$out")"
  got_fc="$("$PY" -c 'import json,sys; print(str(json.load(open(sys.argv[1]))["false_claim"]).lower())' "$out")"
  if [[ "$got_cat" != "$want_cat" ]]; then
    echo "FAIL $name: got category=$got_cat want $want_cat"; fail=1
  elif [[ "$want_fc" != "null" && "$got_fc" != "$want_fc" ]]; then
    echo "FAIL $name: got false_claim=$got_fc want $want_fc"; fail=1
  else
    echo "PASS $name: category=$got_cat false_claim=$got_fc"
  fi
done < <("$PY" -c '
import json, sys
for e in json.load(open(sys.argv[1])):
    fc = "null" if e["expected_false_claim"] is None else str(e["expected_false_claim"]).lower()
    print("\t".join([e["name"], e["repo_dir"], e["final_message"], e["expected_category"], fc]))
' "$SELFTEST/manifest.json")

exit "$fail"
