#!/bin/bash
# Stop the batch download process

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.batch_download.pid"

echo "=================================="
echo "Stopping Batch Download"
echo "=================================="
echo ""

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    echo "No active process found."
    echo "The batch download is not running."
    exit 0
fi

# Read PID
PID=$(cat "$PID_FILE")

# Check if process is running
if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "Process not running (PID: $PID)"
    echo "Removing stale PID file..."
    rm -f "$PID_FILE"
    exit 0
fi

# Stop the process
echo "Stopping process (PID: $PID)..."
kill "$PID"

# Wait for process to stop
echo "Waiting for process to terminate..."
TIMEOUT=30
COUNTER=0

while ps -p "$PID" > /dev/null 2>&1; do
    sleep 1
    COUNTER=$((COUNTER + 1))
    
    if [ $COUNTER -ge $TIMEOUT ]; then
        echo ""
        echo "Process did not terminate gracefully."
        echo "Force killing process..."
        kill -9 "$PID"
        sleep 2
        break
    fi
    
    echo -n "."
done

echo ""

# Check if process stopped
if ps -p "$PID" > /dev/null 2>&1; then
    echo "Failed to stop process!"
    exit 1
else
    echo "Process stopped successfully."
    rm -f "$PID_FILE"
fi

echo ""
echo "To restart, run: ./run_batch.sh"

