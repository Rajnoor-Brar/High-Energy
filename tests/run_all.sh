#!/bin/sh
# Run all test_*.exe binaries in tests/.
# Exit 0 if every test passes; exit 1 after running all tests if any failed.
# Exit code 77 from a test binary is treated as "skip" (missing fixture).
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0
SKIP=0
FAIL=0

for exe in "$SCRIPT_DIR"/test_*.exe; do
    [ -f "$exe" ] || continue
    name="$(basename "$exe")"
    printf "Running %-40s... " "$name"
    set +e
    "$exe"
    status=$?
    set -e
    if [ "$status" -eq 0 ]; then
        echo "PASS"
        PASS=$((PASS + 1))
    elif [ "$status" -eq 77 ]; then
        echo "SKIP (fixture missing)"
        SKIP=$((SKIP + 1))
    else
        echo "FAIL (exit $status)"
        FAIL=$((FAIL + 1))
    fi
done

echo ""
echo "Results: $PASS passed, $SKIP skipped, $FAIL failed"
[ "$FAIL" -eq 0 ]
