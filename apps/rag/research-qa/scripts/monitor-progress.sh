#!/bin/bash
# ORION RAG Progress Monitoring Script
# Quick commands to check batch processing status
#
# Usage:
#   ./monitor-progress.sh              # Show latest progress
#   ./monitor-progress.sh --watch      # Watch continuously
#   ./monitor-progress.sh --summary    # Full summary
#
# Created: 2025-11-20

# Find latest log file
LOG_DIR="/tmp/orion-logs"
LATEST_LOG=$(ls -t "$LOG_DIR"/orion-overnight-*.log 2>/dev/null | head -1)

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
    tail -f "$LATEST_LOG" | grep --line-buffered -E "PROGRESS REPORT|✓|✗|ERROR SUMMARY|ORCHESTRATION COMPLETE"

elif [ "$1" = "--summary" ]; then
    # Full summary
    echo "======================================================================"
    echo "INGESTION SUMMARY"
    echo "======================================================================"
    echo ""

    # Latest progress report
    echo "Latest Progress Report:"
    grep "PROGRESS REPORT" "$LATEST_LOG" | tail -1
    echo ""

    # Counts
    UPLOADED=$(grep -c "^✓" "$LATEST_LOG" 2>/dev/null || echo "0")
    FAILED=$(grep -c "^✗ \[FAILED\]" "$LATEST_LOG" 2>/dev/null || echo "0")

    echo "Documents Uploaded: $UPLOADED"
    echo "Documents Failed:   $FAILED"
    echo ""

    # Last 10 processed files
    echo "Last 10 Processed Files:"
    grep "^✓" "$LATEST_LOG" | tail -10
    echo ""

    # Recent errors
    echo "Recent Errors:"
    grep "^✗ \[FAILED\]" "$LATEST_LOG" | tail -5
    echo ""

    # Check if completed
    if grep -q "ORCHESTRATION COMPLETE" "$LATEST_LOG"; then
        echo "✅ Batch processing COMPLETED"
        echo ""
        grep "ORCHESTRATION COMPLETE" -A 20 "$LATEST_LOG" | head -25
    else
        echo "⏳ Batch processing IN PROGRESS..."
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
        grep "PROGRESS REPORT" -A 10 "$LATEST_LOG" | tail -11
    else
        echo "No progress reports yet. Processing may have just started."
    fi
    echo ""

    # Counts
    UPLOADED=$(grep -c "^✓" "$LATEST_LOG" 2>/dev/null || echo "0")
    FAILED=$(grep -c "^✗ \[FAILED\]" "$LATEST_LOG" 2>/dev/null || echo "0")

    echo "Documents Uploaded: $UPLOADED"
    echo "Documents Failed:   $FAILED"
    echo ""

    # Check if still running
    LAST_TIMESTAMP=$(grep "PROGRESS REPORT" "$LATEST_LOG" | tail -1 | grep -o "[0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}")
    if [ -n "$LAST_TIMESTAMP" ]; then
        echo "Last activity: $LAST_TIMESTAMP"
    fi
    echo ""

    # Check if completed
    if grep -q "ORCHESTRATION COMPLETE" "$LATEST_LOG"; then
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
