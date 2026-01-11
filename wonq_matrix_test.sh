#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# WoNQ Matrix Test - QonQrete v2.0.4-stable
# ═══════════════════════════════════════════════════════════════════════════════
# Runs 90 parallel tests across all combinations of:
#   - Briq Sensitivity: 0-9 (10 values)
#   - Cycle Amount: 1-9 (9 values)
#   - Total: 10 × 9 = 90 tests
#
# Usage:
#   ./wonq_matrix_test.sh                    # Run all 90 tests
#   ./wonq_matrix_test.sh --dry-run          # Show commands without running
#   ./wonq_matrix_test.sh --parallel 5       # Max 5 parallel (default: all)
#
# Output directories:
#   ./worqspace/qonstructions/mindstaq-test-b{0-9}c{1-9}/
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
DRY_RUN=false
MAX_PARALLEL=0  # 0 = unlimited
SLEEP_BETWEEN=1 # seconds between starts
TASQ_FILE=""    # Default: uses -a for autowonqnet

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --parallel)
            MAX_PARALLEL="$2"
            shift 2
            ;;
        --sleep)
            SLEEP_BETWEEN="$2"
            shift 2
            ;;
        --tasq)
            TASQ_FILE="$2"
            shift 2
            ;;
        --help)
            echo "WoNQ Matrix Test v2.0.4"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run         Show commands without executing"
            echo "  --parallel N      Limit to N parallel processes (default: unlimited)"
            echo "  --sleep N         Seconds between starts (default: 1)"
            echo "  --tasq FILE       Use specific tasq file instead of -a"
            echo "  --help            Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Banner
echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════════════════════════════════════════╗"
echo "║                        WoNQ MATRIX TEST v2.0.4                                ║"
echo "║                     90 Parallel QonQrete Test Runs                            ║"
echo "╠═══════════════════════════════════════════════════════════════════════════════╣"
echo "║  Briq Sensitivity: 0-9 (10 values)                                            ║"
echo "║  Cycle Amount:     1-9 (9 values)                                             ║"
echo "║  Total Tests:      90                                                         ║"
echo "╚═══════════════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if qonqrete.sh exists
if [[ ! -f "./qonqrete.sh" ]]; then
    echo -e "${RED}ERROR: qonqrete.sh not found in current directory!${NC}"
    echo "Make sure you're running this from the qonqrete root directory."
    exit 1
fi

# Create log directory
LOG_DIR="./wonq_matrix_logs"
mkdir -p "$LOG_DIR"

# Track PIDs for parallel execution
declare -a PIDS
declare -a NAMES
RUNNING=0
COMPLETED=0
FAILED=0

# Function to wait for a slot if max parallel is set
wait_for_slot() {
    if [[ $MAX_PARALLEL -gt 0 ]]; then
        while [[ $RUNNING -ge $MAX_PARALLEL ]]; do
            # Check which processes have finished
            for i in "${!PIDS[@]}"; do
                if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
                    wait "${PIDS[$i]}" && ((COMPLETED++)) || ((FAILED++))
                    ((RUNNING--))
                    unset "PIDS[$i]"
                    unset "NAMES[$i]"
                fi
            done
            sleep 0.5
        done
    fi
}

# Start time
START_TIME=$(date +%s)
echo -e "${YELLOW}Starting at: $(date)${NC}"
echo ""

# Counter
COUNT=0

# Run all 90 combinations
for briq in {0..9}; do
    for cycle in {1..9}; do
        ((COUNT++))
        
        NAME="mindstaq-test-b${briq}c${cycle}"
        
        # Build command
        if [[ -n "$TASQ_FILE" ]]; then
            CMD="./qonqrete.sh -t \"$TASQ_FILE\" -b $briq -c $cycle -n \"$NAME\""
        else
            CMD="./qonqrete.sh -a -b $briq -c $cycle -n \"$NAME\""
        fi
        
        if $DRY_RUN; then
            echo -e "${BLUE}[$COUNT/90]${NC} $CMD"
        else
            # Wait for slot if parallel limit set
            wait_for_slot
            
            # Run in background
            LOG_FILE="$LOG_DIR/${NAME}.log"
            echo -e "${GREEN}[$COUNT/90]${NC} Starting $NAME (log: $LOG_FILE)"
            
            eval "$CMD" > "$LOG_FILE" 2>&1 &
            
            PIDS+=($!)
            NAMES+=("$NAME")
            ((RUNNING++))
            
            # Sleep between starts
            sleep $SLEEP_BETWEEN
        fi
    done
done

if $DRY_RUN; then
    echo ""
    echo -e "${YELLOW}DRY RUN - No tests were actually started${NC}"
    echo "Total commands: $COUNT"
    exit 0
fi

echo ""
echo -e "${YELLOW}All 90 tests launched! Waiting for completion...${NC}"
echo ""

# Wait for all remaining processes
for i in "${!PIDS[@]}"; do
    if wait "${PIDS[$i]}"; then
        ((COMPLETED++))
        echo -e "${GREEN}✓${NC} ${NAMES[$i]} completed"
    else
        ((FAILED++))
        echo -e "${RED}✗${NC} ${NAMES[$i]} failed"
    fi
done

# End time
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}WoNQ Matrix Test Complete!${NC}"
echo ""
echo "Total tests:    90"
echo "Completed:      $COMPLETED"
echo "Failed:         $FAILED"
echo "Duration:       ${DURATION}s ($((DURATION/60))m $((DURATION%60))s)"
echo ""
echo "Logs saved to:  $LOG_DIR/"
echo "Results in:     ./worqspace/qonstructions/mindstaq-test-b*c*/"
echo ""

# Summary table
echo -e "${CYAN}Quick Summary:${NC}"
echo "┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐"
echo "│ B\\C │  1  │  2  │  3  │  4  │  5  │  6  │  7  │  8  │  9  │"
echo "├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤"

for briq in {0..9}; do
    printf "│  %d  │" $briq
    for cycle in {1..9}; do
        NAME="mindstaq-test-b${briq}c${cycle}"
        if [[ -d "./worqspace/qonstructions/$NAME" ]]; then
            printf " ${GREEN}✓${NC}   │"
        else
            printf " ${RED}✗${NC}   │"
        fi
    done
    echo ""
done
echo "└─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘"

echo ""
echo -e "${YELLOW}To analyze results, run:${NC}"
echo "  ./wonq_analyzer.sh  # (if available)"
echo "  or check individual logs in $LOG_DIR/"
