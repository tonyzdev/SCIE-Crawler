#!/bin/bash
# Check the status of the batch download process

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.batch_download.pid"
BATCH_LOG="$SCRIPT_DIR/batch_log.json"
LOG_DIR="$SCRIPT_DIR/logs"

echo "=================================="
echo "Batch Download Status"
echo "=================================="
echo ""

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    echo "Status: NOT RUNNING"
    echo "No active process found."
    echo ""
    
    # Show last run log if exists
    if [ -d "$LOG_DIR" ]; then
        LAST_LOG=$(ls -t "$LOG_DIR"/run_*.log 2>/dev/null | head -1)
        if [ -n "$LAST_LOG" ]; then
            echo "Last log file: $LAST_LOG"
            echo ""
            echo "Last 20 lines of log:"
            echo "---"
            tail -20 "$LAST_LOG"
        fi
    fi
    exit 0
fi

# Read PID
PID=$(cat "$PID_FILE")

# Check if process is running
if ps -p "$PID" > /dev/null 2>&1; then
    echo "Status: RUNNING"
    echo "PID: $PID"
    echo ""
    
    # Show process info
    echo "Process info:"
    ps -p "$PID" -o pid,etime,cmd
    echo ""
    
    # Show current log file
    CURRENT_LOG=$(ls -t "$LOG_DIR"/run_*.log 2>/dev/null | head -1)
    if [ -n "$CURRENT_LOG" ]; then
        echo "Current log: $CURRENT_LOG"
        echo ""
        echo "Last 20 lines of log:"
        echo "---"
        tail -20 "$CURRENT_LOG"
    fi
    
    echo ""
    echo "To view live log:"
    echo "  tail -f $CURRENT_LOG"
else
    echo "Status: STOPPED"
    echo "PID file exists but process is not running."
    echo "Removing stale PID file..."
    rm -f "$PID_FILE"
fi

echo ""

# Show batch statistics if log exists
if [ -f "$BATCH_LOG" ]; then
    echo "=================================="
    echo "Progress Statistics"
    echo "=================================="
    
    # Use Python to parse JSON and show statistics
    python3 -c "
import json
try:
    with open('$BATCH_LOG', 'r') as f:
        data = json.load(f)
    
    total = len(data)
    success = sum(1 for x in data if x.get('status') == 'success')
    skipped = sum(1 for x in data if x.get('status') == 'skipped')
    failed = sum(1 for x in data if x.get('status') == 'failed')
    not_found = sum(1 for x in data if x.get('status') == 'not_found')
    articles = sum(x.get('articles_count', 0) for x in data if x.get('status') in ['success', 'skipped'])
    
    print(f'Total journals processed: {total}')
    print(f'Successfully downloaded: {success}')
    print(f'Skipped (already exists): {skipped}')
    print(f'Not found in database: {not_found}')
    print(f'Failed (errors): {failed}')
    print(f'Total articles: {articles}')
    
    if total > 0:
        last = data[-1]
        print(f\"\\nLast processed: Line {last.get('line_number', 'N/A')} - {last.get('journal_name', 'N/A')}\")
        print(f\"Status: {last.get('status', 'N/A')}\")
except Exception as e:
    print(f'Error reading batch log: {e}')
" 2>/dev/null || echo "Unable to parse batch log"
fi

echo ""

