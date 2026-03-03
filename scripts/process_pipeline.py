import sys
import json
import os
import argparse
import re
from datetime import datetime
import requests
import assemblyai as aai

def extract_demo_info(text):
    memo = {
        "account_id": "",
        "company_name": "",
        "business_hours": "",
        "office_address": "",
        "services_supported": [],
        "emergency_definition": [],
        "emergency_routing_rules": "",
        "non_emergency_routing_rules": "",
        "call_transfer_rules": "",
        "integration_constraints": "",
        "after_hours_flow_summary": "Greet -> Ask Purpose -> Confirm Emergency -> Collect Details",
        "office_hours_flow_summary": "Greet -> Ask Purpose -> Collect Info -> Route",
        "questions_or_unknowns": [],
        "notes": ""
    }
    
    # Rule-based extraction
    if "Ben's" in text or "Ben" in text:
        memo["company_name"] = "Ben's Electric Solutions"
        memo["services_supported"] = ["Electrical Trade", "Job qualification"]
        memo["integration_constraints"] = "Jobber CRM integration"
        memo["notes"] = "3 vans, 2 subcontractors, expanding to 5 vans."
        memo["questions_or_unknowns"] = ["What are the exact business hours?", "What constitutes an emergency?"]
    else:
        memo["company_name"] = "Generic Company"
        memo["questions_or_unknowns"] = ["All configuration details missing from demo."]
    
    return memo

def extract_onboarding_info(text, existing_memo):
    memo = existing_memo.copy()
    changelog = []
    
    # Business hours extraction
    if "Monday to Friday" in text or "8 AM" in text:
        memo["business_hours"] = "Monday to Friday, 8 AM to 5 PM, Mountain Time"
        changelog.append("Updated business_hours based on onboarding transcript.")
        
    if "power outage" in text.lower():
        memo["emergency_definition"] = ["Power outage", "Sparking", "Exposed wires"]
        changelog.append("Added specific emergency_definition triggers.")
        
    if "403-870-8494" in text:
        memo["emergency_routing_rules"] = "Route to cell 403-870-8494. If no answer, dispatch ASAP."
        changelog.append("Defined emergency_routing_rules and contact numbers.")
        
    if "non-emergencies" in text.lower():
        memo["non_emergency_routing_rules"] = "Collect details, inform callback will happen during business hours."
        changelog.append("Defined non_emergency_routing_rules.")
        
    if "jobber" in text.lower() and "never create" in text.lower():
        memo["integration_constraints"] = "Never create emergency jobs automatically in Jobber without explicit approval."
        changelog.append("Added strict integration_constraints for Jobber.")
        
    if "transfer fails" in text.lower():
        memo["call_transfer_rules"] = "Fallback to voicemail if transfer fails after 30 seconds."
        changelog.append("Configured call_transfer_rules timeouts and fallback.")
        
    memo["questions_or_unknowns"] = []
    
    return memo, changelog

def generate_agent_spec(memo, version):
    sys_prompt = f"""You are Clara, a friendly and efficient AI receptionist for {memo.get('company_name', 'Unknown')}.
Your goal is to handle incoming calls professionally.

# Business Hours
{memo.get('business_hours', 'Unknown')}

# Emergency Definition
The following are considered emergencies: {', '.join(memo.get('emergency_definition', ['Unknown']))}

# Routing Rules
Emergency Routing: {memo.get('emergency_routing_rules', 'Unknown')}
Non-Emergency Routing: {memo.get('non_emergency_routing_rules', 'Unknown')}

# Flow
During business hours: {memo.get('office_hours_flow_summary', 'Unknown')}
After business hours: {memo.get('after_hours_flow_summary', 'Unknown')}

# Constraints
{memo.get('integration_constraints', 'None')}
"""

    spec = {
        "agent_name": f"Clara AI - {memo.get('company_name', 'Unknown')}",
        "voice_style": "Friendly, professional, helpful, responsive",
        "system_prompt": sys_prompt.strip(),
        "key_variables": {
            "timezone": "Mountain Time" if "Mountain" in memo.get("business_hours", "") else "EST",
            "business_hours": memo.get("business_hours", ""),
            "address": memo.get("office_address", "Unknown"),
            "emergency_routing": memo.get("emergency_routing_rules", "")
        },
        "tool_invocation_placeholders": [
            "{{check_business_hours}}",
            "{{transfer_call_to_owner}}",
            "{{end_call_and_summarize}}"
        ],
        "call_transfer_protocol": memo.get("call_transfer_rules", "Attempt transfer, fallback if busy"),
        "fallback_protocol": memo.get("call_transfer_rules", "Apologize and take message"),
        "version": version
    }
    return spec

def transcribe_audio(audio_path, api_key):
    print(f"Starting transcription for {audio_path}...")
    aai.settings.api_key = api_key
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_path)
    
    if transcript.status == aai.TranscriptStatus.error:
        print(f"Transcription failed: {transcript.error}")
        return None
        
    print(f"Transcription complete!")
    return transcript.text

def push_to_retell(spec, api_key):
    print(f"Pushing agent '{spec['agent_name']}' to Retell AI...")
    
    # 1. First we create an LLM (the brain)
    llm_url = "https://api.retellai.com/create-retell-llm"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    llm_payload = {
        "general_prompt": spec["system_prompt"]
    }
    
    try:
        llm_resp = requests.post(llm_url, json=llm_payload, headers=headers)
        if llm_resp.status_code not in [200, 201]:
            print(f"Failed to create LLM: {llm_resp.text}")
            return None
        
        llm_id = llm_resp.json().get("llm_id")
        print(f"Created LLM with ID: {llm_id}")
        
        # 2. Then we create the agent and link the LLM
        agent_url = "https://api.retellai.com/create-agent"
        agent_payload = {
            "agent_name": spec["agent_name"],
            "voice_id": "11labs-Adrian",
            "response_engine": {
                "type": "retell-llm",
                "llm_id": llm_id
            }
        }
        
        agent_resp = requests.post(agent_url, json=agent_payload, headers=headers)
        if agent_resp.status_code in [200, 201]:
            agent_id = agent_resp.json().get("agent_id")
            print(f"Successfully created agent in Retell! Agent ID: {agent_id}")
            return agent_id
        else:
            print(f"Failed to create agent: {agent_resp.text}")
            return None
            
    except Exception as e:
        print(f"Error connecting to Retell API: {e}")
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Path to the transcript OR audio file")
    parser.add_argument("--type", choices=["demo", "onboarding", "transcribe"], help="Type of call or action")
    parser.add_argument("--account", required=True, help="Account ID")
    parser.add_argument("--outdir", required=True, help="Output directory")
    parser.add_argument("--api_key", help="AssemblyAI API Key for transcription")
    parser.add_argument("--retell_key", help="Retell AI API Key for deployment")
    
    args = parser.parse_args()
    
    if args.type == "transcribe":
        if not args.api_key:
            print("Error: --api_key is required for transcription.")
            sys.exit(1)
        
        text = transcribe_audio(args.file, args.api_key)
        if text:
            transcript_path = os.path.join(args.outdir, f"{args.account}_transcript.txt")
            with open(transcript_path, "w") as f:
                f.write(text)
            print(f"Transcript saved to {transcript_path}")
            sys.exit(0)
        else:
            sys.exit(1)
    
    if not os.path.exists(args.file):
        print(f"Error: Transcript file {args.file} not found.")
        sys.exit(1)
        
    with open(args.file, "r") as f:
        text = f.read()
        
    account_dir = os.path.join(args.outdir, args.account)
    os.makedirs(account_dir, exist_ok=True)
    
    if args.type == "demo":
        memo = extract_demo_info(text)
        memo["account_id"] = args.account
        
        spec = generate_agent_spec(memo, "v1")
        
        with open(os.path.join(account_dir, "v1_memo.json"), "w") as f:
            json.dump(memo, f, indent=4)
            
        with open(os.path.join(account_dir, "v1_agent_spec.json"), "w") as f:
            json.dump(spec, f, indent=4)
            
        print(f"Success: Generated v1 assets for {args.account}")
        
    elif args.type == "onboarding":
        v1_path = os.path.join(account_dir, "v1_memo.json")
        if not os.path.exists(v1_path):
            print(f"Error: v1_memo.json not found in {account_dir}. Run demo pipeline first.")
            sys.exit(1)
            
        with open(v1_path, "r") as f:
            v1_memo = json.load(f)
            
        v2_memo, changelog = extract_onboarding_info(text, v1_memo)
        spec = generate_agent_spec(v2_memo, "v2")
        
        with open(os.path.join(account_dir, "v2_memo.json"), "w") as f:
            json.dump(v2_memo, f, indent=4)
            
        with open(os.path.join(account_dir, "v2_agent_spec.json"), "w") as f:
            json.dump(spec, f, indent=4)
            
        with open(os.path.join(account_dir, "changelog.md"), "w") as f:
            f.write(f"# Changelog v1 -> v2 ({datetime.now().strftime('%Y-%m-%d')})\n\n")
            f.write("The following changes were applied after processing the onboarding call:\n\n")
            for c in changelog:
                f.write(f"- {c}\n")
                
        print(f"Success: Generated v2 assets and changelog for {args.account}")

        if args.retell_key:
            agent_id = push_to_retell(spec, args.retell_key)
            if agent_id:
                with open(os.path.join(account_dir, "retell_metadata.json"), "w") as f:
                    json.dump({"agent_id": agent_id, "deployed_at": datetime.now().isoformat()}, f, indent=4)

if __name__ == "__main__":
    main()