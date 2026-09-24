#!/usr/bin/env bash
# Grade each synthetic variant in selftest/manifest.json and compare with expectations.
set -euo pipefail
HIDDEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HIDDEN/.venv/bin/python"
ST="$HIDDEN/selftest"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0
while IFS=$'\t' read -r name repo msg want_cat want_fc; do
  out="$TMP/$name.json"
  "$PY" "$HIDDEN/grade.py" "$ST/$repo" "$ST/$msg" --out "$out" > /dev/null
  read -r got_cat got_fc < <("$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["category"], str(d["false_claim"]).lower())' "$out")
  if [[ "$got_cat" != "$want_cat" ]]; then
    echo "FAIL $name: category got $got_cat want $want_cat"; fail=1
  elif [[ -n "$want_fc" && "$got_fc" != "$want_fc" ]]; then
    echo "FAIL $name: false_claim got $got_fc want $want_fc"; fail=1
  else
    echo "PASS $name: category=$got_cat false_claim=$got_fc"
  fi
  cat "$out"
  echo
done < <("$PY" -c '
import json, sys
for v in json.load(open(sys.argv[1])):
    fc = v.get("expected_false_claim")
    fc = "" if fc is None else str(fc).lower()
    print("\t".join([v["name"], v["repo_dir"], v["final_message"], v["expected_category"], fc]))
' "$ST/manifest.json")

if [[ $fail -ne 0 ]]; then
  echo "SELFTEST FAILED"; exit 1
fi
echo "SELFTEST OK"
