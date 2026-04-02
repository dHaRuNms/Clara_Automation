#!/usr/bin/env python3
"""
Clara AI – API Server & Dashboard
====================================
Flask server that serves the premium web dashboard and exposes
API endpoints for processing transcripts and deploying agents.
"""

import os
import sys
import json
import logging
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask, request, jsonify, send_from_directory

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from clara_engine import ClaraEngine, ClaraMultiAgent
from retell_deployer import RetellDeployer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("clara-server")

app = Flask(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIST = os.path.join(BASE_DIR, "dashboard", "dist")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs", "accounts")
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, "transcripts")

# Configure Flask to serve React production build
app.static_folder = os.path.join(DASHBOARD_DIST, "assets")
app.static_url_path = '/assets'


# ── Dashboard Serving ──
@app.route("/")
def serve_dashboard():
    return send_from_directory(DASHBOARD_DIST, "index.html")


@app.route("/<path:path>")
def serve_static_files(path):
    """Serve static files from React build, fallback to index.html for client routing."""
    filepath = os.path.join(DASHBOARD_DIST, path)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        return send_from_directory(DASHBOARD_DIST, path)
    return send_from_directory(DASHBOARD_DIST, "index.html")
# ── API: Health ──
@app.route("/api/health")
def health():
    nvidia_key = bool(os.environ.get("NVIDIA_API_KEY", ""))
    return jsonify({
        "status": "ok",
        "service": "clara-ai",
        "mode": "multi-agent" if nvidia_key else "classic",
        "nvidia_nim": nvidia_key
    })


# ── API: Mode Status ──
@app.route("/api/mode")
def mode_status():
    nvidia_key = bool(os.environ.get("NVIDIA_API_KEY", ""))
    return jsonify({
        "mode": "multi-agent" if nvidia_key else "classic",
        "nvidia_nim": nvidia_key,
        "models": {
            "extractor": os.environ.get("NVIDIA_EXTRACTOR_MODEL", "mistralai/mixtral-8x22b-instruct-v0.1"),
            "researcher": os.environ.get("NVIDIA_RESEARCH_MODEL", "meta/llama-3.1-405b-instruct"),
            "default": os.environ.get("NVIDIA_DEFAULT_MODEL", "meta/llama-3.3-70b-instruct"),
        } if nvidia_key else {"fallback": "gemini-2.0-flash"}
    })


# ── API: List Accounts ──
@app.route("/api/accounts")
def list_accounts():
    accounts = []
    if os.path.isdir(OUTPUT_DIR):
        for account_id in sorted(os.listdir(OUTPUT_DIR)):
            account_dir = os.path.join(OUTPUT_DIR, account_id)
            if not os.path.isdir(account_dir):
                continue

            info = {
                "account_id": account_id,
                "versions": [],
                "deployed": False,
                "company": "",
                "agent_id": "",
                "deployed_at": ""
            }

            for version in ["v1", "v2"]:
                memo_path = os.path.join(account_dir, f"{version}_memo.json")
                if os.path.exists(memo_path):
                    info["versions"].append(version)
                    try:
                        with open(memo_path) as f:
                            memo = json.load(f)
                        info["company"] = memo.get("company_name", "")
                    except Exception:
                        pass

            deploy_path = os.path.join(account_dir, "retell_deployment.json")
            if os.path.exists(deploy_path):
                try:
                    with open(deploy_path) as f:
                        deploy = json.load(f)
                    info["deployed"] = True
                    info["agent_id"] = deploy.get("agent_id", "")
                    info["deployed_at"] = deploy.get("deployed_at", "")
                except Exception:
                    pass

            accounts.append(info)

    return jsonify({"accounts": accounts})


# ── API: Get Agent Details ──
@app.route("/api/agent/<account_id>")
def get_agent(account_id):
    account_dir = os.path.join(OUTPUT_DIR, account_id)
    if not os.path.isdir(account_dir):
        return jsonify({"error": "Account not found"}), 404

    result = {}

    # Load latest memo
    for version in ["v2", "v1"]:
        memo_path = os.path.join(account_dir, f"{version}_memo.json")
        if os.path.exists(memo_path):
            with open(memo_path) as f:
                result["memo"] = json.load(f)
            break

    # Load latest LLM config
    for version in ["v2", "v1"]:
        llm_path = os.path.join(account_dir, f"{version}_retell_llm.json")
        if os.path.exists(llm_path):
            with open(llm_path) as f:
                result["llm_config"] = json.load(f)
            break

    # Load latest agent config
    for version in ["v2", "v1"]:
        agent_path = os.path.join(account_dir, f"{version}_retell_agent.json")
        if os.path.exists(agent_path):
            with open(agent_path) as f:
                result["agent_config"] = json.load(f)
            break

    # Load deployment info
    deploy_path = os.path.join(account_dir, "retell_deployment.json")
    if os.path.exists(deploy_path):
        with open(deploy_path) as f:
            result["deployment"] = json.load(f)

    # Load changelog
    changelog_path = os.path.join(account_dir, "changelog.md")
    if os.path.exists(changelog_path):
        with open(changelog_path) as f:
            result["changelog"] = f.read()

    return jsonify(result)


# ── API: Process Transcript ──
@app.route("/api/process/<account_id>", methods=["POST"])
def process_account(account_id):
    engine = ClaraMultiAgent()

    # Find transcript files
    demo_file = os.path.join(TRANSCRIPTS_DIR, f"{account_id}_demo.txt")
    onboarding_file = os.path.join(TRANSCRIPTS_DIR, f"{account_id}_onboarding.txt")

    results = []

    # Process demo
    if os.path.exists(demo_file):
        with open(demo_file) as f:
            text = f.read()
        memo, agent_trace = engine.analyze_demo(text, account_id)
        engine.save_outputs(memo, agent_trace=agent_trace, output_dir=OUTPUT_DIR)
        results.append({"type": "demo", "status": "success", "agent_trace_length": len(agent_trace)})
        log.info(f"✅ Demo processed for {account_id} | Agents: {len(agent_trace)}")

    # Process onboarding
    if os.path.exists(onboarding_file):
        v1_path = os.path.join(OUTPUT_DIR, account_id, "v1_memo.json")
        if os.path.exists(v1_path):
            with open(v1_path) as f:
                v1_memo = json.load(f)
            with open(onboarding_file) as f:
                text = f.read()
            v2_memo, changelog, agent_trace = engine.analyze_onboarding(text, v1_memo)
            engine.save_outputs(v2_memo, changelog=changelog, agent_trace=agent_trace, output_dir=OUTPUT_DIR)
            results.append({"type": "onboarding", "status": "success", "changes": len(changelog), "agent_trace_length": len(agent_trace)})
            log.info(f"✅ Onboarding processed for {account_id} | Changes: {len(changelog)}")

    if not results:
        return jsonify({"status": "error", "message": f"No transcript files found for {account_id}"}), 404

    return jsonify({"status": "success", "results": results, "mode": "multi-agent" if engine.available else "classic"})


# ── API: Deploy to Retell ──
@app.route("/api/deploy/<account_id>", methods=["POST"])
def deploy_account(account_id):
    account_dir = os.path.join(OUTPUT_DIR, account_id)

    # Find latest configs
    llm_config = None
    agent_config = None
    for version in ["v2", "v1"]:
        llm_path = os.path.join(account_dir, f"{version}_retell_llm.json")
        agent_path = os.path.join(account_dir, f"{version}_retell_agent.json")
        if os.path.exists(llm_path) and os.path.exists(agent_path):
            with open(llm_path) as f:
                llm_config = json.load(f)
            with open(agent_path) as f:
                agent_config = json.load(f)
            break

    if not llm_config or not agent_config:
        return jsonify({"status": "error", "message": "No configs found. Process the account first."}), 404

    deployer = RetellDeployer()
    result = deployer.redeploy(account_dir, llm_config, agent_config)
    return jsonify(result)


# ── API: Batch Process & Deploy ──
@app.route("/api/batch", methods=["POST"])
def batch_process():
    engine = ClaraMultiAgent()
    deployer = RetellDeployer()
    results = []

    if not os.path.isdir(TRANSCRIPTS_DIR):
        return jsonify({"status": "error", "message": "No transcripts directory"}), 404

    files = sorted(os.listdir(TRANSCRIPTS_DIR))

    # Phase 1: Demos
    for fname in files:
        if "_demo" in fname and fname.endswith(".txt"):
            account_id = fname.replace("_demo.txt", "")
            try:
                with open(os.path.join(TRANSCRIPTS_DIR, fname)) as f:
                    text = f.read()
                memo, agent_trace = engine.analyze_demo(text, account_id)
                engine.save_outputs(memo, agent_trace=agent_trace, output_dir=OUTPUT_DIR)
                results.append({"account": account_id, "type": "demo", "status": "success"})
            except Exception as e:
                results.append({"account": account_id, "type": "demo", "status": "error", "error": str(e)})

    # Phase 2: Onboarding
    for fname in files:
        if "_onboarding" in fname and fname.endswith(".txt"):
            account_id = fname.replace("_onboarding.txt", "")
            v1_path = os.path.join(OUTPUT_DIR, account_id, "v1_memo.json")
            if not os.path.exists(v1_path):
                continue
            try:
                with open(v1_path) as f:
                    v1_memo = json.load(f)
                with open(os.path.join(TRANSCRIPTS_DIR, fname)) as f:
                    text = f.read()
                v2_memo, changelog, agent_trace = engine.analyze_onboarding(text, v1_memo)
                engine.save_outputs(v2_memo, changelog=changelog, agent_trace=agent_trace, output_dir=OUTPUT_DIR)
                results.append({"account": account_id, "type": "onboarding", "status": "success"})
            except Exception as e:
                results.append({"account": account_id, "type": "onboarding", "status": "error", "error": str(e)})

    # Phase 3: Deploy all
    if deployer.api_key:
        for account_id in sorted(os.listdir(OUTPUT_DIR)):
            account_dir = os.path.join(OUTPUT_DIR, account_id)
            if not os.path.isdir(account_dir):
                continue
            for version in ["v2", "v1"]:
                llm_path = os.path.join(account_dir, f"{version}_retell_llm.json")
                agent_path = os.path.join(account_dir, f"{version}_retell_agent.json")
                if os.path.exists(llm_path) and os.path.exists(agent_path):
                    with open(llm_path) as f:
                        llm_config = json.load(f)
                    with open(agent_path) as f:
                        agent_config = json.load(f)
                    deploy_result = deployer.redeploy(account_dir, llm_config, agent_config)
                    results.append({"account": account_id, "type": "deploy", "status": deploy_result.get("status", "error")})
                    break

    success = sum(1 for r in results if r.get("status") == "success")
    failed = sum(1 for r in results if r.get("status") == "error")

    return jsonify({"results": results, "success": success, "failed": failed, "mode": "multi-agent" if engine.available else "classic"})


# ── API: Call History ──
@app.route("/api/calls/<account_id>")
def get_calls(account_id):
    account_dir = os.path.join(OUTPUT_DIR, account_id)
    deploy_path = os.path.join(account_dir, "retell_deployment.json")

    if not os.path.exists(deploy_path):
        return jsonify({"calls": []})

    with open(deploy_path) as f:
        deploy = json.load(f)

    deployer = RetellDeployer()
    agent_id = deploy.get("agent_id")
    calls = deployer.list_calls(agent_id)

    return jsonify({"calls": calls if isinstance(calls, list) else []})


# ── API: Agent Trace Log ──
@app.route("/api/agent-log/<account_id>")
def get_agent_log(account_id):
    """Return per-agent execution trace for a processed account."""
    account_dir = os.path.join(OUTPUT_DIR, account_id)
    trace = None
    for version in ["v2", "v1"]:
        trace_path = os.path.join(account_dir, f"{version}_agent_trace.json")
        if os.path.exists(trace_path):
            with open(trace_path) as f:
                trace = json.load(f)
            break
    if not trace:
        return jsonify({"agent_trace": [], "mode": "classic", "message": "No agent trace found. Classic Gemini mode was used or account not processed."})
    return jsonify(trace)


# ── API: Callers (People who called in) ──
@app.route("/api/callers/<account_id>")
def get_callers(account_id):
    """Get caller records parsed from Retell post-call analysis."""
    account_dir = os.path.join(OUTPUT_DIR, account_id)
    deploy_path = os.path.join(account_dir, "retell_deployment.json")

    if not os.path.exists(deploy_path):
        return jsonify({"callers": []})

    with open(deploy_path) as f:
        deploy = json.load(f)

    deployer = RetellDeployer()
    agent_id = deploy.get("agent_id")
    calls_raw = deployer.list_calls(agent_id)

    callers = []
    if isinstance(calls_raw, list):
        for call in calls_raw:
            analysis = call.get("call_analysis") or {}
            custom = analysis.get("custom_analysis_data") or {}
            transcript = call.get("transcript", "")

            # Extract caller name from custom data or try to parse from transcript
            caller_name = custom.get("caller_name", "")
            if not caller_name and transcript:
                # Try to find name from transcript patterns like "my name is X" or "I'm X"
                import re
                name_match = re.search(r"(?:my name is|I'm|this is|I am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", transcript)
                if name_match:
                    caller_name = name_match.group(1)

            # Phone: from_number is the most reliable source
            caller_phone = custom.get("caller_phone") or call.get("from_number", "")

            # Build caller record
            caller = {
                "call_id": call.get("call_id", ""),
                "timestamp": call.get("start_timestamp", 0),
                "duration_sec": round((call.get("duration_ms") or 0) / 1000),
                "status": call.get("call_status", ""),
                "disconnection": call.get("disconnection_reason", ""),
                # Caller info
                "name": caller_name or "Caller",
                "phone": caller_phone,
                "call_type": custom.get("call_type", call.get("call_type", "")),
                "problem": custom.get("service_requested", ""),
                "urgency": custom.get("urgency_level", ""),
                "address": custom.get("caller_address", ""),
                "action_taken": custom.get("action_taken", ""),
                "schedule": custom.get("preferred_schedule", ""),
                "summary": analysis.get("call_summary", ""),
                # Standard analysis
                "sentiment": analysis.get("user_sentiment", ""),
                "successful": analysis.get("call_successful", None),
                "in_voicemail": analysis.get("in_voicemail", False),
                # Extra
                "direction": call.get("direction", ""),
                "recording_url": call.get("recording_url", ""),
            }
            callers.append(caller)

    # Sort by most recent first
    callers.sort(key=lambda c: c.get("timestamp", 0), reverse=True)

    return jsonify({"callers": callers})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    log.info(f"═══════════════════════════════════════════════")
    log.info(f"  Clara AI – Dashboard & API Server")
    log.info(f"  http://localhost:{port}")
    log.info(f"═══════════════════════════════════════════════")
    app.run(host="0.0.0.0", port=port, debug=True)
