#!/bin/bash
# View the latest log file

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"

# Check if logs directory exists
if [ ! -d "$LOG_DIR" ]; then
    echo "No logs directory found."
    exit 1
fi

# Get the latest log file
LATEST_LOG=$(ls -t "$LOG_DIR"/run_*.log 2>/dev/null | head -1)

if [ -z "$LATEST_LOG" ]; then
    echo "No log files found."
    exit 1
fi

echo "Viewing latest log: $LATEST_LOG"
echo "=================================="
echo ""

# Check if -f flag is passed for follow mode
if [ "$1" = "-f" ] || [ "$1" = "--follow" ]; then
    tail -f "$LATEST_LOG"
else
    # Show last 50 lines by default
    LINES=${1:-50}
    tail -n "$LINES" "$LATEST_LOG"
    echo ""
    echo "=================================="
    echo "Showing last $LINES lines"
    echo "Use '$0 -f' to follow in real-time"
    echo "Use '$0 <number>' to show specific number of lines"
fi

