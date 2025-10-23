#!/bin/bash
# Background batch download script for journal articles
# This script runs the batch download in the background with logging

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/batch_download_journals.py"
INPUT_FILE="$SCRIPT_DIR/SCIE-202508-1.txt"
OUTPUT_DIR="$SCRIPT_DIR/output"
LOG_DIR="$SCRIPT_DIR/logs"
BATCH_LOG="$SCRIPT_DIR/batch_log.json"
PID_FILE="$SCRIPT_DIR/.batch_download.pid"

# Create logs directory if not exists
mkdir -p "$LOG_DIR"

# Get current timestamp for log file
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_LOG="$LOG_DIR/run_${TIMESTAMP}.log"

# Default values
START_LINE=1
END_LINE=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--start)
            START_LINE="$2"
            shift 2
            ;;
        -e|--end)
            END_LINE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -s, --start NUM    Start from line number (default: 1)"
            echo "  -e, --end NUM      End at line number (default: all)"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                 # Process all journals"
            echo "  $0 -s 1 -e 100     # Process journals 1-100"
            echo "  $0 -s 500          # Process from line 500 to end"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use -h or --help for usage information"
            exit 1
            ;;
    esac
done

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Error: Batch download is already running (PID: $OLD_PID)"
        echo "If you want to stop it, run: kill $OLD_PID"
        exit 1
    else
        echo "Removing stale PID file..."
        rm -f "$PID_FILE"
    fi
fi

# Build Python command
PYTHON_CMD="python3 $PYTHON_SCRIPT $INPUT_FILE -o $OUTPUT_DIR -l $BATCH_LOG -s $START_LINE"
if [ -n "$END_LINE" ]; then
    PYTHON_CMD="$PYTHON_CMD -e $END_LINE"
fi

# Display information
echo "=================================="
echo "Starting Batch Download"
echo "=================================="
echo "Input file: $INPUT_FILE"
echo "Output directory: $OUTPUT_DIR"
echo "Start line: $START_LINE"
if [ -n "$END_LINE" ]; then
    echo "End line: $END_LINE"
else
    echo "End line: (all remaining)"
fi
echo "Log file: $RUN_LOG"
echo "Batch log: $BATCH_LOG"
echo "=================================="
echo ""

# Start the process in background
echo "Starting process in background..."
nohup $PYTHON_CMD > "$RUN_LOG" 2>&1 &
PID=$!

# Save PID to file
echo $PID > "$PID_FILE"

echo "Process started successfully!"
echo "PID: $PID"
echo ""
echo "To monitor progress:"
echo "  tail -f $RUN_LOG"
echo ""
echo "To check if still running:"
echo "  ps -p $PID"
echo ""
echo "To stop the process:"
echo "  kill $PID"
echo ""
echo "Log file: $RUN_LOG"

