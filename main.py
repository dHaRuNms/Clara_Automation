#!/usr/bin/env python3
"""
Clara AI – Main CLI Orchestrator
==================================
End-to-end pipeline: Transcript → Gemini Analysis → Retell Deployment.

Usage:
  python main.py process --transcript transcripts/ben_demo.txt --type demo --account ben
  python main.py process --transcript transcripts/ben_onboarding.txt --type onboarding --account ben
  python main.py deploy --account ben
  python main.py status
  python main.py batch
"""

import argparse
import json
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from clara_engine import ClaraEngine
from retell_deployer import RetellDeployer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("clara")

OUTPUT_DIR = "outputs/accounts"
TRANSCRIPTS_DIR = "transcripts"


def cmd_process(args):
    """Process a transcript file."""
    engine = ClaraEngine()
    
    if not os.path.exists(args.transcript):
        log.error(f"File not found: {args.transcript}")
        sys.exit(1)

    with open(args.transcript, "r") as f:
        text = f.read()

    if args.type == "demo":
        log.info(f"{'='*60}")
        log.info(f"📋 DEMO PIPELINE | Account: {args.account}")
        log.info(f"{'='*60}")
        memo = engine.analyze_demo(text, args.account)
        outputs = engine.save_outputs(memo, output_dir=OUTPUT_DIR)

        log.info(f"\n✅ Demo pipeline complete for '{args.account}'")
        log.info(f"   Company: {memo.get('company_name', 'N/A')}")
        log.info(f"   Services: {', '.join(memo.get('services_supported', []))}")
        log.info(f"   Unknowns: {len(memo.get('questions_or_unknowns', []))}")
        print(json.dumps({"status": "success", "version": "v1", "outputs": outputs}, indent=2))

    elif args.type == "onboarding":
        log.info(f"{'='*60}")
        log.info(f"📋 ONBOARDING PIPELINE | Account: {args.account}")
        log.info(f"{'='*60}")
        
        v1_path = os.path.join(OUTPUT_DIR, args.account, "v1_memo.json")
        if not os.path.exists(v1_path):
            log.error("v1_memo.json not found. Run demo pipeline first.")
            sys.exit(1)

        with open(v1_path, "r") as f:
            v1_memo = json.load(f)

        v2_memo, changelog = engine.analyze_onboarding(text, v1_memo)
        outputs = engine.save_outputs(v2_memo, changelog, output_dir=OUTPUT_DIR)

        log.info(f"\n✅ Onboarding pipeline complete for '{args.account}'")
        log.info(f"   Changes: {len(changelog)}")
        for c in changelog:
            log.info(f"   • {c}")
        print(json.dumps({"status": "success", "version": "v2", "changes": len(changelog), "outputs": outputs}, indent=2))


def cmd_deploy(args):
    """Deploy an account's agent to Retell AI."""
    account_dir = os.path.join(OUTPUT_DIR, args.account)

    # Find latest version config
    for version in ["v2", "v1"]:
        llm_path = os.path.join(account_dir, f"{version}_retell_llm.json")
        agent_path = os.path.join(account_dir, f"{version}_retell_agent.json")
        if os.path.exists(llm_path) and os.path.exists(agent_path):
            break
    else:
        log.error(f"No Retell configs found for account '{args.account}'. Run 'process' first.")
        sys.exit(1)

    log.info(f"{'='*60}")
    log.info(f"🚀 DEPLOYING TO RETELL | Account: {args.account} | Version: {version}")
    log.info(f"{'='*60}")

    with open(llm_path, "r") as f:
        llm_config = json.load(f)
    with open(agent_path, "r") as f:
        agent_config = json.load(f)

    deployer = RetellDeployer()
    result = deployer.redeploy(account_dir, llm_config, agent_config)

    if result.get("status") in ["success", "updated"]:
        log.info(f"\n✅ Deployment {'updated' if result['status'] == 'updated' else 'complete'}!")
        log.info(f"   Agent ID: {result['agent_id']}")
        log.info(f"   LLM ID:   {result['llm_id']}")
        log.info(f"   Test it at: https://dashboard.retellai.com")
    else:
        log.error(f"❌ Deployment failed: {result}")

    print(json.dumps(result, indent=2))


def cmd_status(args):
    """Show status of all accounts and deployed agents."""
    deployer = RetellDeployer()

    log.info(f"{'='*60}")
    log.info(f"📊 CLARA AI STATUS REPORT")
    log.info(f"{'='*60}")

    if not os.path.isdir(OUTPUT_DIR):
        log.info("No accounts found.")
        return

    accounts = []
    for account_id in sorted(os.listdir(OUTPUT_DIR)):
        account_dir = os.path.join(OUTPUT_DIR, account_id)
        if not os.path.isdir(account_dir):
            continue

        info = {"account_id": account_id, "versions": [], "deployed": False}

        for version in ["v1", "v2"]:
            memo_path = os.path.join(account_dir, f"{version}_memo.json")
            if os.path.exists(memo_path):
                with open(memo_path, "r") as f:
                    memo = json.load(f)
                info["versions"].append(version)
                info["company"] = memo.get("company_name", "")

        deploy_path = os.path.join(account_dir, "retell_deployment.json")
        if os.path.exists(deploy_path):
            with open(deploy_path, "r") as f:
                deploy = json.load(f)
            info["deployed"] = True
            info["agent_id"] = deploy.get("agent_id", "")
            info["deployed_at"] = deploy.get("deployed_at", "")

        accounts.append(info)

        status = "🟢 LIVE" if info["deployed"] else "🟡 DRAFT"
        log.info(f"  {status} {account_id}: {info.get('company', 'N/A')} | Versions: {', '.join(info['versions'])}")
        if info["deployed"]:
            log.info(f"       Agent: {info.get('agent_id', 'N/A')}")

    # Also check Retell for deployed agents
    if deployer.api_key:
        agents = deployer.list_agents()
        if isinstance(agents, list):
            log.info(f"\n  Retell Platform: {len(agents)} total agents")

    print(json.dumps(accounts, indent=2))


def cmd_batch(args):
    """Process all transcripts and deploy."""
    if not os.path.isdir(TRANSCRIPTS_DIR):
        log.error(f"Transcripts directory not found: {TRANSCRIPTS_DIR}")
        sys.exit(1)

    log.info(f"{'='*60}")
    log.info(f"📦 BATCH PROCESSING ALL TRANSCRIPTS")
    log.info(f"{'='*60}")

    files = sorted(os.listdir(TRANSCRIPTS_DIR))
    demo_files = [f for f in files if "_demo" in f and f.endswith(".txt")]
    onboarding_files = [f for f in files if "_onboarding" in f and f.endswith(".txt")]

    results = []

    # Phase 1: Demo files
    for fname in demo_files:
        account = fname.replace("_demo.txt", "")
        log.info(f"\n📋 Processing demo: {fname}")
        try:
            engine = ClaraEngine()
            with open(os.path.join(TRANSCRIPTS_DIR, fname), "r") as f:
                text = f.read()
            memo = engine.analyze_demo(text, account)
            engine.save_outputs(memo, output_dir=OUTPUT_DIR)
            results.append({"account": account, "type": "demo", "status": "success"})
            log.info(f"   ✅ {account} demo processed")
        except Exception as e:
            results.append({"account": account, "type": "demo", "status": "error", "error": str(e)})
            log.error(f"   ❌ {account} demo failed: {e}")

    # Phase 2: Onboarding files
    for fname in onboarding_files:
        account = fname.replace("_onboarding.txt", "")
        log.info(f"\n📋 Processing onboarding: {fname}")
        try:
            engine = ClaraEngine()
            v1_path = os.path.join(OUTPUT_DIR, account, "v1_memo.json")
            if not os.path.exists(v1_path):
                log.warning(f"   ⚠️ Skipping {account} onboarding – no v1 memo found")
                continue
            with open(v1_path, "r") as f:
                v1_memo = json.load(f)
            with open(os.path.join(TRANSCRIPTS_DIR, fname), "r") as f:
                text = f.read()
            v2_memo, changelog = engine.analyze_onboarding(text, v1_memo)
            engine.save_outputs(v2_memo, changelog, output_dir=OUTPUT_DIR)
            results.append({"account": account, "type": "onboarding", "status": "success", "changes": len(changelog)})
            log.info(f"   ✅ {account} onboarding processed ({len(changelog)} changes)")
        except Exception as e:
            results.append({"account": account, "type": "onboarding", "status": "error", "error": str(e)})
            log.error(f"   ❌ {account} onboarding failed: {e}")

    # Phase 3: Deploy all
    if not args.no_deploy:
        deployer = RetellDeployer()
        if deployer.api_key:
            log.info(f"\n🚀 Deploying all accounts to Retell...")
            for account_id in sorted(os.listdir(OUTPUT_DIR)):
                account_dir = os.path.join(OUTPUT_DIR, account_id)
                if not os.path.isdir(account_dir):
                    continue
                for version in ["v2", "v1"]:
                    llm_path = os.path.join(account_dir, f"{version}_retell_llm.json")
                    agent_path = os.path.join(account_dir, f"{version}_retell_agent.json")
                    if os.path.exists(llm_path) and os.path.exists(agent_path):
                        with open(llm_path, "r") as f:
                            llm_config = json.load(f)
                        with open(agent_path, "r") as f:
                            agent_config = json.load(f)
                        result = deployer.redeploy(account_dir, llm_config, agent_config)
                        log.info(f"   {'✅' if result.get('status') != 'error' else '❌'} {account_id}: {result.get('status', 'error')}")
                        break

    # Summary
    success = sum(1 for r in results if r.get("status") == "success")
    failed = sum(1 for r in results if r.get("status") == "error")
    log.info(f"\n{'='*60}")
    log.info(f"📊 BATCH COMPLETE: {success} success, {failed} failed, {len(results)} total")
    log.info(f"{'='*60}")

    print(json.dumps({"results": results, "success": success, "failed": failed}, indent=2))


def cmd_calls(args):
    """View call history for an account."""
    deployer = RetellDeployer()
    account_dir = os.path.join(OUTPUT_DIR, args.account)
    deploy_path = os.path.join(account_dir, "retell_deployment.json")

    if not os.path.exists(deploy_path):
        log.error(f"No deployment found for '{args.account}'.")
        sys.exit(1)

    with open(deploy_path, "r") as f:
        deploy = json.load(f)

    agent_id = deploy.get("agent_id")
    calls = deployer.list_calls(agent_id, limit=args.limit)

    if isinstance(calls, list):
        log.info(f"📞 {len(calls)} calls for {args.account}")
        for call in calls:
            log.info(f"  {call.get('start_timestamp', 'N/A')} | {call.get('call_status', 'N/A')} | {call.get('duration_ms', 0)//1000}s")
    else:
        log.info(f"Call history: {json.dumps(calls, indent=2)}")

    print(json.dumps(calls, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(
        description="Clara AI – Voice Agent Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py process --transcript transcripts/ben_demo.txt --type demo --account ben
  python main.py process --transcript transcripts/ben_onboarding.txt --type onboarding --account ben
  python main.py deploy --account ben
  python main.py status
  python main.py batch
  python main.py calls --account ben
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # process
    p = subparsers.add_parser("process", help="Process a transcript")
    p.add_argument("--transcript", required=True, help="Path to transcript file")
    p.add_argument("--type", required=True, choices=["demo", "onboarding"])
    p.add_argument("--account", required=True, help="Account ID")

    # deploy
    p = subparsers.add_parser("deploy", help="Deploy agent to Retell AI")
    p.add_argument("--account", required=True, help="Account ID")

    # status
    subparsers.add_parser("status", help="Show all accounts status")

    # batch
    p = subparsers.add_parser("batch", help="Process all transcripts and deploy")
    p.add_argument("--no-deploy", action="store_true", help="Skip Retell deployment")

    # calls
    p = subparsers.add_parser("calls", help="View call history")
    p.add_argument("--account", required=True, help="Account ID")
    p.add_argument("--limit", type=int, default=20, help="Max calls to show")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "process": cmd_process,
        "deploy": cmd_deploy,
        "status": cmd_status,
        "batch": cmd_batch,
        "calls": cmd_calls,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
