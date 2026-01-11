#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Simple 90 Parallel Test Runner for QonQrete v2.0.4
# ═══════════════════════════════════════════════════════════════════════════════
# Runs all combinations of briq-sens (0-9) x cycles (1-9) = 90 tests
# 
# Usage:
#   cd qonqrete_v2.0.4-stable
#   ./run_90_tests.sh
#
# Output:
#   Logs:    ./wonq_matrix_logs/mindstaq-test-b*c*.log
#   Results: ./worqspace/qonstructions/mindstaq-test-b*c*/
# ═══════════════════════════════════════════════════════════════════════════════

set -e

echo "╔═══════════════════════════════════════════════════════════════════════════════╗"
echo "║                    WoNQ MATRIX TEST - 90 Parallel Runs                        ║"
echo "║                    QonQrete v2.0.4-stable                                     ║"
echo "╚═══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Create log directory
mkdir -p wonq_matrix_logs

# Check qonqrete.sh exists
if [[ ! -f "./qonqrete.sh" ]]; then
    echo "ERROR: qonqrete.sh not found! Run from qonqrete root directory."
    exit 1
fi

echo "Starting 90 tests at $(date)..."
echo ""

COUNT=0

for briq in {0..9}; do
    for cycle in {1..9}; do
        ((COUNT++))
        NAME="mindstaq-test-b${briq}c${cycle}"
        
        echo "[$COUNT/90] Launching $NAME..."
        ./qonqrete.sh -a -b $briq -c $cycle -n "$NAME" > "wonq_matrix_logs/${NAME}.log" 2>&1 &
        
        sleep 1
    done
done

echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "✓ All 90 tests launched!"
echo ""
echo "Logs:    ./wonq_matrix_logs/"
echo "Results: ./worqspace/qonstructions/mindstaq-test-b*c*/"
echo ""
echo "Commands:"
echo "  Monitor progress: watch 'ls worqspace/qonstructions/ | wc -l'"
echo "  Wait for all:     wait"
echo "  Check failures:   grep -l 'ERROR\|FAILED' wonq_matrix_logs/*.log"
echo "═══════════════════════════════════════════════════════════════════════════════"
