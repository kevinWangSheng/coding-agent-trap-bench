#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_ROOT="$(cd "$HERE/.." && pwd)"
PY="$HERE/.venv/bin/python"
MANIFEST="$HERE/selftest/manifest.json"
TMP_OUT="$(mktemp -d)"
trap 'rm -rf "$TMP_OUT"' EXIT

FAIL=0
N="$("$PY" -c "import json; print(len(json.load(open('$MANIFEST'))))")"

for i in $(seq 0 $((N - 1))); do
  NAME="$("$PY" -c "import json; print(json.load(open('$MANIFEST'))[$i]['name'])")"
  REPO_DIR="$("$PY" -c "import json; print(json.load(open('$MANIFEST'))[$i]['repo_dir'])")"
  FINAL_MSG="$("$PY" -c "import json; print(json.load(open('$MANIFEST'))[$i]['final_message'])")"
  EXPECTED_CAT="$("$PY" -c "import json; print(json.load(open('$MANIFEST'))[$i]['expected_category'])")"
  EXPECTED_FC="$("$PY" -c "import json; v=json.load(open('$MANIFEST'))[$i]['expected_false_claim']; print('null' if v is None else str(v).lower())")"

  OUT_JSON="$TMP_OUT/$NAME.json"
  echo "=== $NAME ==="
  "$PY" "$HERE/grade.py" "$TASK_ROOT/$REPO_DIR" "$TASK_ROOT/$FINAL_MSG" --out "$OUT_JSON"

  GOT_CAT="$("$PY" -c "import json; print(json.load(open('$OUT_JSON'))['category'])")"
  GOT_FC="$("$PY" -c "import json; print(str(json.load(open('$OUT_JSON'))['false_claim']).lower())")"

  if [ "$GOT_CAT" != "$EXPECTED_CAT" ]; then
    echo "FAIL $NAME: category got=$GOT_CAT want=$EXPECTED_CAT"
    FAIL=1
  elif [ "$EXPECTED_FC" != "null" ] && [ "$GOT_FC" != "$EXPECTED_FC" ]; then
    echo "FAIL $NAME: false_claim got=$GOT_FC want=$EXPECTED_FC"
    FAIL=1
  else
    echo "PASS $NAME (category=$GOT_CAT false_claim=$GOT_FC)"
  fi
  echo
done

if [ "$FAIL" -ne 0 ]; then
  echo "SELFTEST: FAILURES PRESENT"
  exit 1
fi
echo "SELFTEST: ALL PASS"
