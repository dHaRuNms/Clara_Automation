import os
import sys
import json

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from clara_engine import ClaraMultiAgent
from retell_deployer import RetellDeployer

from fastmcp import FastMCP

mcp = FastMCP("Clara-Multi-Agent-MCP")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs", "accounts")
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, "transcripts")

@mcp.tool()
def process_account(account_id: str) -> str:
    """Run the Clara multi-agent pipeline (Extractor -> Researcher + QA -> Config Generator) to process transcripts."""
    engine = ClaraMultiAgent()
    demo_file = os.path.join(TRANSCRIPTS_DIR, f"{account_id}_demo.txt")
    onboarding_file = os.path.join(TRANSCRIPTS_DIR, f"{account_id}_onboarding.txt")
    
    results = []
    
    if os.path.exists(demo_file):
        with open(demo_file) as f:
            text = f.read()
        memo, agent_trace = engine.analyze_demo(text, account_id)
        engine.save_outputs(memo, agent_trace=agent_trace, output_dir=OUTPUT_DIR)
        results.append(f"Demo processed (Agent trace: {len(agent_trace)} steps).")
        
    if os.path.exists(onboarding_file):
        v1_path = os.path.join(OUTPUT_DIR, account_id, "v1_memo.json")
        if os.path.exists(v1_path):
            with open(v1_path) as f:
                v1_memo = json.load(f)
            with open(onboarding_file) as f:
                text = f.read()
            v2_memo, changelog, agent_trace = engine.analyze_onboarding(text, v1_memo)
            engine.save_outputs(v2_memo, changelog=changelog, agent_trace=agent_trace, output_dir=OUTPUT_DIR)
            results.append(f"Onboarding processed (Changes: {len(changelog)}, Agent trace: {len(agent_trace)} steps).")
            
    if not results:
        return f"Error: No transcript files found for account '{account_id}' in {TRANSCRIPTS_DIR}"
        
    return "\n".join(results)

@mcp.tool()
def deploy_account(account_id: str) -> str:
    """Deploy the processed configuration for an account directly to Retell AI."""
    account_dir = os.path.join(OUTPUT_DIR, account_id)
    
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
        return f"Error: No Retell configs found for '{account_id}'. Process the account first."
        
    deployer = RetellDeployer()
    result = deployer.redeploy(account_dir, llm_config, agent_config)
    return f"Deployment status: {result.get('status')} - Agent ID: {result.get('agent_id')}"

@mcp.tool()
def list_live_calls(account_id: str) -> str:
    """Fetch live call logs for a deployed Retell agent associated with an account."""
    account_dir = os.path.join(OUTPUT_DIR, account_id)
    deploy_path = os.path.join(account_dir, "retell_deployment.json")
    
    if not os.path.exists(deploy_path):
        return f"No deployment found for '{account_id}'."
        
    with open(deploy_path) as f:
        deploy = json.load(f)
        
    deployer = RetellDeployer()
    agent_id = deploy.get("agent_id")
    calls = deployer.list_calls(agent_id)
    
    if not calls:
        return f"No calls found for agent {agent_id}."
        
    # Just format a nice summary
    summary = f"Found {len(calls)} calls for agent {agent_id}:\n"
    for c in calls[:5]:
        status = c.get('call_status', 'unknown')
        dur = c.get('duration_ms', 0) // 1000
        analysis = c.get('call_analysis', {}).get('call_summary', 'No summary')
        summary += f"- {status} ({dur}s): {analysis}\n"
        
    return summary

if __name__ == "__main__":
    mcp.run()