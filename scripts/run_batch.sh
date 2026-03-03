#!/bin/bash

# A script to run the pipeline for all files in a dataset
# Supports running inside or outside of Docker

TRANSCRIPTS_DIR=$1
OUT_DIR=$2

# Detect script location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PIPELINE_SCRIPT="$SCRIPT_DIR/process_pipeline.py"

# If script exists in /data (Docker) use that, otherwise use local
if [ -f "/data/scripts/process_pipeline.py" ]; then
    PIPELINE_SCRIPT="/data/scripts/process_pipeline.py"
fi

echo "Starting batch processing using $PIPELINE_SCRIPT..."

# First process all demo calls
for file in "$TRANSCRIPTS_DIR"/*demo*.txt; do
    if [ -f "$file" ]; then
        filename=$(basename -- "$file")
        account="${filename%%_demo*}"
        
        echo "Processing DEMO for account: $account"
        python3 "$PIPELINE_SCRIPT" --file "$file" --type demo --account "$account" --outdir "$OUT_DIR" --retell_key "$RETELL_API_KEY"
    fi
done

# Then process all onboarding calls
for file in "$TRANSCRIPTS_DIR"/*onboarding*.txt; do
    if [ -f "$file" ]; then
        filename=$(basename -- "$file")
        account="${filename%%_onboarding*}"
        
        echo "Processing ONBOARDING for account: $account"
        python3 "$PIPELINE_SCRIPT" --file "$file" --type onboarding --account "$account" --outdir "$OUT_DIR" --retell_key "$RETELL_API_KEY"
    fi
done

echo "Batch processing completed successfully!"