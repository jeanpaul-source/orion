#!/bin/bash
# ORION Harvest Progress Monitoring Script
# Quick commands to check batch harvesting status
#
# Usage:
#   ./monitor-harvest.sh              # Show latest progress
#   ./monitor-harvest.sh --watch      # Watch continuously
#   ./monitor-harvest.sh --summary    # Full summary
#
# Created: 2025-11-20

# Find latest log file
LOG_DIR="/tmp/orion-harvest-logs"
LATEST_LOG=$(ls -t "$LOG_DIR"/harvest-*.log 2>/dev/null | head -1)

if [ -z "$LATEST_LOG" ]; then
    echo "No log files found in $LOG_DIR"
    exit 1
fi

echo "Monitoring: $LATEST_LOG"
echo ""

if [ "$1" = "--watch" ]; then
    # Continuous monitoring
    echo "Watching progress (Ctrl+C to stop)..."
    echo ""
    tail -f "$LATEST_LOG" | grep --line-buffered -E "PROGRESS REPORT|Found:|Downloaded:|ERROR SUMMARY|BATCH HARVEST COMPLETE"

elif [ "$1" = "--summary" ]; then
    # Full summary
    echo "======================================================================"
    echo "HARVEST SUMMARY"
    echo "======================================================================"
    echo ""

    # Latest progress report
    echo "Latest Progress Report:"
    grep "PROGRESS REPORT" "$LATEST_LOG" | tail -1
    echo ""

    # Counts
    TERMS_PROCESSED=$(grep "Terms processed:" "$LATEST_LOG" | tail -1 | grep -o "[0-9]*" | head -1 || echo "0")
    FOUND=$(grep "Documents found:" "$LATEST_LOG" | tail -1 | grep -o "[0-9]*" | head -1 || echo "0")
    DOWNLOADED=$(grep "Documents downloaded:" "$LATEST_LOG" | tail -1 | grep -o "[0-9]*" | head -1 || echo "0")
    SKIPPED=$(grep "Documents skipped:" "$LATEST_LOG" | tail -1 | grep -o "[0-9]*" | head -1 || echo "0")

    echo "Terms Processed: $TERMS_PROCESSED"
    echo "Documents Found: $FOUND"
    echo "Documents Downloaded: $DOWNLOADED"
    echo "Documents Skipped: $SKIPPED"
    echo ""

    # Last 10 searches
    echo "Last 10 Searches:"
    grep "^\[" "$LATEST_LOG" | grep -E "\[[0-9]+/[0-9]+\]" | tail -10
    echo ""

    # Recent errors
    echo "Recent Errors:"
    grep "ERROR:" "$LATEST_LOG" | tail -5
    echo ""

    # Check if completed
    if grep -q "BATCH HARVEST COMPLETE" "$LATEST_LOG"; then
        echo "✅ Batch harvesting COMPLETED"
        echo ""
        grep "BATCH HARVEST COMPLETE" -A 15 "$LATEST_LOG" | head -20
    else
        echo "⏳ Batch harvesting IN PROGRESS..."
    fi

else
    # Quick status (default)
    echo "Quick Status:"
    echo "-------------"
    echo ""

    # Latest progress
    PROGRESS=$(grep "PROGRESS REPORT" "$LATEST_LOG" | tail -1)
    if [ -n "$PROGRESS" ]; then
        echo "Latest Progress:"
        grep "PROGRESS REPORT" -A 9 "$LATEST_LOG" | tail -10
    else
        echo "No progress reports yet. Processing may have just started."
    fi
    echo ""

    # Counts
    TERMS_PROCESSED=$(grep "Terms processed:" "$LATEST_LOG" | tail -1 | grep -o "[0-9]*" | head -1 || echo "0")
    DOWNLOADED=$(grep "Documents downloaded:" "$LATEST_LOG" | tail -1 | grep -o "[0-9]*" | head -1 || echo "0")

    echo "Terms Processed: $TERMS_PROCESSED"
    echo "Documents Downloaded: $DOWNLOADED"
    echo ""

    # Check if still running
    LAST_TIMESTAMP=$(grep "PROGRESS REPORT" "$LATEST_LOG" | tail -1 | grep -o "[0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}")
    if [ -n "$LAST_TIMESTAMP" ]; then
        echo "Last activity: $LAST_TIMESTAMP"
    fi
    echo ""

    # Check if completed
    if grep -q "BATCH HARVEST COMPLETE" "$LATEST_LOG"; then
        echo "✅ Status: COMPLETED"
    else
        echo "⏳ Status: IN PROGRESS"
    fi
fi

echo ""
echo "Monitoring Options:"
echo "  Quick status:  $0"
echo "  Full summary:  $0 --summary"
echo "  Live watch:    $0 --watch"
echo "  View log:      less $LATEST_LOG"
echo "  Tail log:      tail -f $LATEST_LOG"
echo ""
