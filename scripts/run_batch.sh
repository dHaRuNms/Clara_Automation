#!/bin/bash
# ═══════════════════════════════════════════
# Clara AI – Batch Transcript Processing
# ═══════════════════════════════════════════
# Usage (inside Docker):  bash /data/scripts/run_batch.sh /data/transcripts /data/outputs/accounts
# Usage (local):          bash scripts/run_batch.sh transcripts outputs/accounts

set -euo pipefail

TRANSCRIPTS_DIR="${1:-transcripts}"
OUT_DIR="${2:-outputs/accounts}"

# Detect script location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PIPELINE_SCRIPT="$SCRIPT_DIR/process_pipeline.py"

# Docker path fallback
if [ -f "/data/scripts/process_pipeline.py" ]; then
    PIPELINE_SCRIPT="/data/scripts/process_pipeline.py"
fi

# API Keys from environment
GEMINI_KEY="${GEMINI_API_KEY:-}"
RETELL_KEY="${RETELL_API_KEY:-}"

echo ""
echo "════════════════════════════════════════════"
echo "  Clara AI – Batch Processing Pipeline"
echo "════════════════════════════════════════════"
echo "  Transcripts Dir : $TRANSCRIPTS_DIR"
echo "  Output Dir       : $OUT_DIR"
echo "  Gemini API       : $([ -n "$GEMINI_KEY" ] && echo '✅ Configured' || echo '⚠️  Not set (rule-based mode)')"
echo "  Retell API       : $([ -n "$RETELL_KEY" ] && echo '✅ Configured' || echo '⏭  Skipped')"
echo "════════════════════════════════════════════"
echo ""

SUCCESS=0
FAILED=0

# ── Phase 1: Process all DEMO calls first (creates v1) ──
echo "▶ Phase 1: Demo Calls (v1 generation)"
echo "───────────────────────────────────────"

for file in "$TRANSCRIPTS_DIR"/*demo*.txt; do
    [ -f "$file" ] || continue
    filename=$(basename -- "$file")
    account="${filename%%_demo*}"

    echo -n "  Processing DEMO for [$account]... "

    if python3 "$PIPELINE_SCRIPT" \
        --file "$file" \
        --type demo \
        --account "$account" \
        --outdir "$OUT_DIR" \
        --gemini_key "$GEMINI_KEY" \
        --retell_key "$RETELL_KEY" \
        > /dev/null 2>&1; then
        echo "✅"
        ((SUCCESS++))
    else
        echo "❌"
        ((FAILED++))
    fi
done

echo ""

# ── Phase 2: Process all ONBOARDING calls (creates v2) ──
echo "▶ Phase 2: Onboarding Calls (v2 generation)"
echo "───────────────────────────────────────────"

for file in "$TRANSCRIPTS_DIR"/*onboarding*.txt; do
    [ -f "$file" ] || continue
    filename=$(basename -- "$file")
    account="${filename%%_onboarding*}"

    echo -n "  Processing ONBOARDING for [$account]... "

    if python3 "$PIPELINE_SCRIPT" \
        --file "$file" \
        --type onboarding \
        --account "$account" \
        --outdir "$OUT_DIR" \
        --gemini_key "$GEMINI_KEY" \
        --retell_key "$RETELL_KEY" \
        > /dev/null 2>&1; then
        echo "✅"
        ((SUCCESS++))
    else
        echo "❌"
        ((FAILED++))
    fi
done

echo ""
echo "════════════════════════════════════════════"
echo "  Results: $SUCCESS succeeded, $FAILED failed"
echo "════════════════════════════════════════════"
echo ""

# Exit with failure if any pipeline failed
[ $FAILED -eq 0 ] || exit 1