#!/usr/bin/env python3
"""
Clara AI – Transcript Processing Pipeline
==========================================
Processes demo and onboarding call transcripts using Google Gemini Flash
to extract structured account memos and generate Retell Agent Specs.

Supports: demo → v1, onboarding → v2 (with diff/changelog), transcribe mode.
"""

import sys
import json
import os
import argparse
import re
import logging
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

try:
    import assemblyai as aai
except ImportError:
    aai = None

# ──────────────────────────────────────────────
# Logging Setup
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("clara-pipeline")

# ──────────────────────────────────────────────
# Account Memo Schema (all required fields)
# ──────────────────────────────────────────────
MEMO_SCHEMA = {
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
    "after_hours_flow_summary": "",
    "office_hours_flow_summary": "",
    "questions_or_unknowns": [],
    "notes": ""
}

# ──────────────────────────────────────────────
# Gemini-Powered Extraction
# ──────────────────────────────────────────────
DEMO_EXTRACTION_PROMPT = """You are a data extraction specialist for Clara AI, an AI voice agent platform for service trade businesses.

Analyze this DEMO CALL transcript and extract structured information. ONLY extract what is EXPLICITLY stated — do NOT invent, assume, or hallucinate any facts. If information is not mentioned, leave the field empty or add it to questions_or_unknowns.

Return a valid JSON object with EXACTLY these fields:
{
  "company_name": "string - the company name if mentioned",
  "business_hours": "string - exact hours if stated, empty if not",
  "office_address": "string - address if mentioned, empty if not",
  "services_supported": ["list of services the company provides"],
  "emergency_definition": ["list of what constitutes an emergency, if discussed"],
  "emergency_routing_rules": "string - how emergency calls should be routed",
  "non_emergency_routing_rules": "string - how non-emergency calls should be handled",
  "call_transfer_rules": "string - transfer timeouts, retries, fallback behavior",
  "integration_constraints": "string - any CRM/system integration rules mentioned",
  "after_hours_flow_summary": "string - summary of after-hours call flow if discussed",
  "office_hours_flow_summary": "string - summary of office-hours call flow if discussed",
  "questions_or_unknowns": ["list of critical missing details that need clarification"],
  "notes": "string - any other relevant details about the business"
}

CRITICAL RULES:
- If a field's information is NOT in the transcript, leave it as empty string "" or empty list []
- Do NOT guess business hours, addresses, or routing rules
- Add genuinely missing critical config items to questions_or_unknowns
- Extract the EXACT wording from the transcript where possible

TRANSCRIPT:
---
{transcript}
---

Respond ONLY with the JSON object, no markdown formatting, no explanation."""


ONBOARDING_EXTRACTION_PROMPT = """You are a data extraction specialist for Clara AI. You are processing an ONBOARDING CALL transcript to update an existing account configuration.

The existing v1 account memo from the demo call is:
```json
{existing_memo}
```

Analyze the onboarding transcript below and extract ALL new or updated configuration details. The onboarding call is configuration-focused and should override or refine demo assumptions.

Return a valid JSON object with TWO keys:
{{
  "updated_fields": {{
    // Include ONLY fields that have new or updated information from the onboarding call.
    // Use the SAME field names as the original memo.
    // If a field was empty/vague in v1 and is now clarified, include it.
    // If a field hasn't changed, do NOT include it.
  }},
  "changelog": [
    // List of human-readable strings describing each change.
    // Format: "Updated <field_name>: <old_value> → <new_value>" or "Added <field_name>: <value>"
  ]
}}

CRITICAL RULES:
- ONLY include fields that are explicitly updated or clarified in the onboarding transcript
- Do NOT copy unchanged fields from v1
- If the onboarding confirms a v1 assumption with the same value, skip it
- Clear the questions_or_unknowns for items that are now answered
- Look for: business hours, timezone, emergency definitions, routing rules, transfer rules, integration constraints, fallback logic

ONBOARDING TRANSCRIPT:
---
{transcript}
---

Respond ONLY with the JSON object, no markdown formatting, no explanation."""


def call_gemini(prompt, gemini_key):
    """Call Gemini Flash API for structured extraction."""
    if genai is None:
        log.error("google-genai package not installed. Install with: pip install google-genai")
        return None

    client = genai.Client(api_key=gemini_key)

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )
        result = json.loads(response.text)
        log.info("Gemini extraction successful.")
        return result
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse Gemini response as JSON: {e}")
        log.debug(f"Raw response: {response.text}")
        try:
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        return None
    except Exception as e:
        log.error(f"Gemini API call failed: {e}")
        return None


def extract_demo_info_gemini(text, gemini_key):
    """Extract demo info using Gemini Flash."""
    prompt = DEMO_EXTRACTION_PROMPT.format(transcript=text)
    result = call_gemini(prompt, gemini_key)

    if result is None:
        log.warning("Gemini extraction failed, falling back to rule-based extraction.")
        return extract_demo_info_rules(text)

    # Merge with schema to ensure all fields exist
    memo = MEMO_SCHEMA.copy()
    for key in memo:
        if key in result:
            memo[key] = result[key]

    return memo


def extract_onboarding_info_gemini(text, existing_memo, gemini_key):
    """Extract onboarding updates using Gemini Flash."""
    prompt = ONBOARDING_EXTRACTION_PROMPT.format(
        transcript=text,
        existing_memo=json.dumps(existing_memo, indent=2)
    )
    result = call_gemini(prompt, gemini_key)

    if result is None:
        log.warning("Gemini extraction failed, falling back to rule-based extraction.")
        return extract_onboarding_info_rules(text, existing_memo)

    # Apply updates to existing memo
    updated_memo = existing_memo.copy()
    updated_fields = result.get("updated_fields", {})
    changelog = result.get("changelog", [])

    for key, value in updated_fields.items():
        if key in updated_memo:
            updated_memo[key] = value

    # Clear questions_or_unknowns for answered items
    if updated_fields:
        answered = [q for q in updated_memo.get("questions_or_unknowns", [])
                    if any(field.lower() in q.lower() for field in updated_fields.keys())]
        remaining = [q for q in updated_memo.get("questions_or_unknowns", []) if q not in answered]
        updated_memo["questions_or_unknowns"] = remaining

    return updated_memo, changelog


# ──────────────────────────────────────────────
# Fallback Rule-Based Extraction (no API needed)
# ──────────────────────────────────────────────
def extract_demo_info_rules(text):
    """Rule-based fallback extraction for demo transcripts."""
    memo = MEMO_SCHEMA.copy()

    # Company name detection
    company_patterns = [
        r"(?:company|business|called|for)\s*(?:is\s*)?[:\s]*([A-Z][A-Za-z'\s]+(?:Solutions|Electric|Services|Protection|HVAC|Plumbing|Sprinkler|Alarm|Fire))",
        r"^Company:\s*(.+)$",
    ]
    for pattern in company_patterns:
        match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
        if match:
            memo["company_name"] = match.group(1).strip()
            break

    # Email
    email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
    if email_match:
        memo["notes"] += f" Contact email: {email_match.group()}"

    # Phone
    phone_match = re.search(r'(\d{3}[-.]?\d{3}[-.]?\d{4})', text)
    if phone_match:
        memo["notes"] += f" Phone: {phone_match.group(1)}"

    # Services
    service_keywords = ["electrical", "plumbing", "hvac", "fire protection", "sprinkler",
                        "alarm", "inspection", "maintenance", "repair"]
    memo["services_supported"] = [s.title() for s in service_keywords if s in text.lower()]

    # CRM Detection
    crm_keywords = ["jobber", "servicetrade", "servicetitan", "housecall pro"]
    for crm in crm_keywords:
        if crm.lower() in text.lower():
            memo["integration_constraints"] = f"{crm.title()} CRM integration"
            break

    # Business hours
    hours_match = re.search(r'(?:hours|open|available)\s*(?:are\s*)?(?:from\s*)?(\d+\s*(?:AM|PM)\s*(?:to|-)\s*\d+\s*(?:AM|PM))', text, re.IGNORECASE)
    if hours_match:
        memo["business_hours"] = hours_match.group(1)

    # Mark unknowns
    unknowns = []
    if not memo["business_hours"]:
        unknowns.append("What are the exact business hours?")
    if not memo["emergency_definition"]:
        unknowns.append("What constitutes an emergency?")
    if not memo["emergency_routing_rules"]:
        unknowns.append("How should emergency calls be routed?")
    memo["questions_or_unknowns"] = unknowns

    memo["notes"] = memo["notes"].strip()
    return memo


def extract_onboarding_info_rules(text, existing_memo):
    """Rule-based fallback extraction for onboarding transcripts."""
    memo = existing_memo.copy()
    changelog = []

    # Business hours
    hours_patterns = [
        r'(?:Monday\s*(?:to|through)\s*\w+),?\s*(\d+\s*(?:AM|am)\s*(?:to|-)\s*\d+\s*(?:PM|pm))',
        r'(\d+\s*(?:AM|am)\s*(?:to|-)\s*\d+\s*(?:PM|pm))',
    ]
    for pattern in hours_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            days_match = re.search(r'(Monday\s*(?:to|through)\s*\w+)', text, re.IGNORECASE)
            tz_match = re.search(r'(Mountain|Pacific|Eastern|Central)\s*Time', text, re.IGNORECASE)
            hours_str = ""
            if days_match:
                hours_str += days_match.group(1) + ", "
            hours_str += match.group(1)
            if tz_match:
                hours_str += f", {tz_match.group(1)} Time"
            memo["business_hours"] = hours_str
            changelog.append(f"Updated business_hours: {hours_str}")
            break

    # Emergency definitions
    emergency_keywords = ["power outage", "sparking", "exposed wires", "fire alarm",
                          "gas leak", "flooding", "sprinkler leak", "electrical fire"]
    found_emergencies = [e.title() for e in emergency_keywords if e in text.lower()]
    if found_emergencies:
        memo["emergency_definition"] = found_emergencies
        changelog.append(f"Added emergency_definition: {', '.join(found_emergencies)}")

    # Emergency routing
    route_match = re.search(r'(?:route|call|contact).*?(\d{3}[-.]?\d{3}[-.]?\d{4})', text, re.IGNORECASE)
    if route_match:
        memo["emergency_routing_rules"] = f"Route to {route_match.group(1)}."
        fallback_match = re.search(r"(?:don't|doesn't|no)\s*answer.*?(dispatch|voicemail|message)", text, re.IGNORECASE)
        if fallback_match:
            memo["emergency_routing_rules"] += f" If no answer, {fallback_match.group(1)} ASAP."
        changelog.append(f"Defined emergency_routing_rules: {memo['emergency_routing_rules']}")

    # Non-emergency rules
    if "non-emergenc" in text.lower():
        memo["non_emergency_routing_rules"] = "Collect details, inform callback during business hours."
        changelog.append("Defined non_emergency_routing_rules.")

    # Integration constraints
    constraint_patterns = [
        (r'never\s+create.*?(?:in|on)\s+(\w+)', "Never create jobs automatically in {0} without approval."),
        (r'do\s+not.*?(?:in|on)\s+(\w+)', "Do not modify {0} without approval."),
    ]
    for pattern, template in constraint_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            memo["integration_constraints"] = template.format(match.group(1))
            changelog.append(f"Updated integration_constraints: {memo['integration_constraints']}")
            break

    # Transfer rules
    transfer_match = re.search(r'(?:transfer\s+fails?).*?(\d+)\s*seconds?.*?(voicemail|fallback|dispatch)', text, re.IGNORECASE)
    if transfer_match:
        memo["call_transfer_rules"] = f"Fallback to {transfer_match.group(2)} if transfer fails after {transfer_match.group(1)} seconds."
        changelog.append(f"Configured call_transfer_rules: {memo['call_transfer_rules']}")

    # Clear answered questions
    memo["questions_or_unknowns"] = []

    return memo, changelog


# ──────────────────────────────────────────────
# Agent Spec Generation (Assignment-Compliant)
# ──────────────────────────────────────────────
def generate_agent_spec(memo, version):
    """Generate a Retell Agent Draft Spec with proper business-hours and after-hours flows."""

    company = memo.get("company_name", "the company")
    hours = memo.get("business_hours", "standard business hours")
    emergency_defs = memo.get("emergency_definition", [])
    emergency_route = memo.get("emergency_routing_rules", "Route to on-call staff.")
    non_emergency = memo.get("non_emergency_routing_rules", "Collect details and confirm callback.")
    transfer_rules = memo.get("call_transfer_rules", "Retry once, then take a message.")
    integration = memo.get("integration_constraints", "")
    services = memo.get("services_supported", [])

    emergency_list = ", ".join(emergency_defs) if emergency_defs else "any life-threatening or safety-critical situation"
    services_list = ", ".join(services) if services else "general services"

    system_prompt = f"""# Persona
You are Clara, a friendly and professional AI receptionist for {company}.
Your tone is warm, helpful, efficient, and precise. You speak naturally and conversationally.

# Company Info
- Company: {company}
- Business Hours: {hours}
- Services: {services_list}

# Business Hours Flow
When receiving calls DURING business hours:
1. **Greeting**: "Hi, thank you for calling {company}! This is Clara. How can I help you today?"
2. **Ask Purpose**: Listen to the caller's need and identify the type of request.
3. **Collect Info**: Ask: "May I have your name and the best number to reach you?"
4. **Route or Transfer**: Based on the request, transfer to the appropriate team member.
5. **Transfer Fail Protocol**: {transfer_rules}
6. **Confirm Next Steps**: Summarize what will happen next for the caller.
7. **Anything Else**: "Is there anything else I can help you with?"
8. **Close**: If no, thank them warmly and end the call.

# After-Hours Flow
When receiving calls OUTSIDE business hours:
1. **Greeting**: "Hi, thank you for calling {company}! This is Clara. I should let you know we're currently outside our regular business hours of {hours}."
2. **Ask Purpose**: "How can I help you?"
3. **Confirm Emergency**: Determine if this is an emergency.
   - Emergency triggers: {emergency_list}
4. **If Emergency**:
   a. Immediately collect: caller name, phone number, and address.
   b. Say: "I understand this is urgent. Let me connect you right away."
   c. Attempt transfer: {emergency_route}
   d. If transfer fails: "I'm sorry I wasn't able to connect you directly. I've logged this as an urgent emergency and someone from our team will contact you as soon as possible."
5. **If Non-Emergency**:
   a. Collect: caller name, phone number, and a brief description of their need.
   b. {non_emergency}
   c. Say: "I've noted your details. A team member will reach out to you during our next business day."
6. **Anything Else**: "Is there anything else I can help you with?"
7. **Close**: Thank them warmly and end the call.

# Critical Constraints
- You MUST collect the caller's name and phone number on every call.
- Do NOT mention "AI", "artificial intelligence", "function calls", or "automation" to the caller.
- Do NOT diagnose technical problems — only collect information and route.
- Keep the conversation focused and efficient. Do not ask unnecessary questions.
- {integration if integration else "No special integration constraints."}
- Always confirm the information you've collected before ending the call.

# Call Transfer Protocol
- Primary transfer method: Direct transfer to the relevant team member or number.
- {transfer_rules}
- Never leave the caller in silence for more than 10 seconds during a transfer attempt.

# Tone Guidelines
- Be empathetic during emergencies ("I understand how stressful this must be")
- Be professional but warm during business hours
- Never rush the caller, but keep the conversation on track"""

    spec = {
        "agent_name": f"Clara AI - {company}",
        "voice_style": "Professional Female",
        "system_prompt": system_prompt.strip(),
        "key_variables": {
            "timezone": _extract_timezone(hours),
            "business_hours": hours,
            "address": memo.get("office_address", ""),
            "emergency_routing": emergency_route,
        },
        "tool_invocation_placeholders": [
            "transfer_call(phone_number)",
            "log_message(caller_name, phone, description, priority)",
            "create_ticket(account_id, caller_info, issue_type)"
        ],
        "call_transfer_protocol": transfer_rules,
        "fallback_protocol": "If transfer fails, apologize, assure follow-up, and log the call.",
        "response_engine": {
            "type": "retell-llm"
        },
        "version": version
    }
    return spec


def _extract_timezone(hours_str):
    """Extract timezone from business hours string."""
    tz_match = re.search(r'(Mountain|Pacific|Eastern|Central|ET|PT|MT|CT|EST|PST|MST|CST)', hours_str, re.IGNORECASE)
    return tz_match.group(1) + " Time" if tz_match else "Not specified"


# ──────────────────────────────────────────────
# Audio Transcription (AssemblyAI)
# ──────────────────────────────────────────────
def transcribe_audio(audio_path, api_key):
    """Transcribe audio using AssemblyAI."""
    if aai is None:
        log.error("assemblyai package not installed.")
        return None

    log.info(f"Starting transcription for {audio_path}...")
    aai.settings.api_key = api_key
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_path)

    if transcript.status == aai.TranscriptStatus.error:
        log.error(f"Transcription failed: {transcript.error}")
        return None

    log.info("Transcription complete!")
    return transcript.text


# ──────────────────────────────────────────────
# Retell AI Deployment (Optional)
# ──────────────────────────────────────────────
def push_to_retell(spec, api_key):
    """Push agent spec to Retell AI API."""
    if requests is None:
        log.error("requests package not installed.")
        return None

    log.info(f"Pushing agent '{spec['agent_name']}' to Retell AI...")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Create LLM first
    try:
        llm_resp = requests.post(
            "https://api.retellai.com/create-retell-llm",
            json={"general_prompt": spec["system_prompt"]},
            headers=headers
        )
        if llm_resp.status_code not in [200, 201]:
            log.error(f"Failed to create LLM: {llm_resp.text}")
            return None

        llm_id = llm_resp.json().get("llm_id")
        log.info(f"Created LLM: {llm_id}")

        # Create Agent
        agent_resp = requests.post(
            "https://api.retellai.com/create-agent",
            json={
                "agent_name": spec["agent_name"],
                "voice_id": "11labs-Adrian",
                "response_engine": {"type": "retell-llm", "llm_id": llm_id}
            },
            headers=headers
        )
        if agent_resp.status_code in [200, 201]:
            agent_id = agent_resp.json().get("agent_id")
            log.info(f"Agent deployed: {agent_id}")
            return agent_id
        else:
            log.error(f"Failed to create agent: {agent_resp.text}")
            return None

    except Exception as e:
        log.error(f"Retell API error: {e}")
        return None


# ──────────────────────────────────────────────
# Main Pipeline
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Clara AI – Transcript Processing Pipeline")
    parser.add_argument("--file", help="Path to the transcript or audio file")
    parser.add_argument("--type", choices=["demo", "onboarding", "transcribe"],
                        help="Pipeline type: demo (v1), onboarding (v2), or transcribe")
    parser.add_argument("--account", required=True, help="Account ID")
    parser.add_argument("--outdir", required=True, help="Output directory root")
    parser.add_argument("--gemini_key", default=os.environ.get("GEMINI_API_KEY", ""),
                        help="Gemini API key (or set GEMINI_API_KEY env var)")
    parser.add_argument("--api_key", default=os.environ.get("ASSEMBLYAI_API_KEY", ""),
                        help="AssemblyAI API key for transcription")
    parser.add_argument("--retell_key", default=os.environ.get("RETELL_API_KEY", ""),
                        help="Retell AI API key for deployment")

    args = parser.parse_args()

    log.info(f"{'='*50}")
    log.info(f"Clara Pipeline | Account: {args.account} | Type: {args.type}")
    log.info(f"{'='*50}")

    # ── Transcribe Mode ──
    if args.type == "transcribe":
        if not args.api_key:
            log.error("--api_key is required for transcription.")
            sys.exit(1)
        text = transcribe_audio(args.file, args.api_key)
        if text:
            out_path = os.path.join(args.outdir, f"{args.account}_transcript.txt")
            with open(out_path, "w") as f:
                f.write(text)
            log.info(f"Transcript saved: {out_path}")
            # Output JSON for n8n to parse
            print(json.dumps({"status": "success", "output": out_path}))
            sys.exit(0)
        else:
            print(json.dumps({"status": "error", "message": "Transcription failed"}))
            sys.exit(1)

    # ── Validate Input ──
    if not os.path.exists(args.file):
        log.error(f"File not found: {args.file}")
        print(json.dumps({"status": "error", "message": f"File not found: {args.file}"}))
        sys.exit(1)

    with open(args.file, "r") as f:
        text = f.read()

    account_dir = os.path.join(args.outdir, args.account)
    os.makedirs(account_dir, exist_ok=True)

    use_gemini = bool(args.gemini_key)
    if use_gemini:
        log.info("Using Gemini Flash for intelligent extraction.")
    else:
        log.info("No Gemini key provided. Using rule-based extraction (limited accuracy).")

    # ── Demo Pipeline (v1) ──
    if args.type == "demo":
        log.info(f"Running Demo Pipeline for {args.account}...")

        if use_gemini:
            memo = extract_demo_info_gemini(text, args.gemini_key)
        else:
            memo = extract_demo_info_rules(text)

        memo["account_id"] = args.account
        spec = generate_agent_spec(memo, "v1")

        # Save outputs
        memo_path = os.path.join(account_dir, "v1_memo.json")
        spec_path = os.path.join(account_dir, "v1_agent_spec.json")

        with open(memo_path, "w") as f:
            json.dump(memo, f, indent=4)
        with open(spec_path, "w") as f:
            json.dump(spec, f, indent=4)

        log.info(f"✅ v1 assets saved to {account_dir}/")
        result = {
            "status": "success",
            "account_id": args.account,
            "pipeline": "demo",
            "version": "v1",
            "outputs": {
                "memo": memo_path,
                "agent_spec": spec_path
            },
            "memo_summary": {
                "company": memo.get("company_name", ""),
                "unknowns_count": len(memo.get("questions_or_unknowns", []))
            }
        }
        print(json.dumps(result))

    # ── Onboarding Pipeline (v2) ──
    elif args.type == "onboarding":
        log.info(f"Running Onboarding Pipeline for {args.account}...")

        v1_path = os.path.join(account_dir, "v1_memo.json")
        if not os.path.exists(v1_path):
            log.error(f"v1_memo.json not found. Run demo pipeline first.")
            print(json.dumps({"status": "error", "message": "v1_memo.json not found. Run demo pipeline first."}))
            sys.exit(1)

        with open(v1_path, "r") as f:
            v1_memo = json.load(f)

        if use_gemini:
            v2_memo, changelog = extract_onboarding_info_gemini(text, v1_memo, args.gemini_key)
        else:
            v2_memo, changelog = extract_onboarding_info_rules(text, v1_memo)

        spec = generate_agent_spec(v2_memo, "v2")

        # Save outputs
        v2_memo_path = os.path.join(account_dir, "v2_memo.json")
        v2_spec_path = os.path.join(account_dir, "v2_agent_spec.json")
        changelog_path = os.path.join(account_dir, "changelog.md")

        with open(v2_memo_path, "w") as f:
            json.dump(v2_memo, f, indent=4)
        with open(v2_spec_path, "w") as f:
            json.dump(spec, f, indent=4)
        with open(changelog_path, "w") as f:
            f.write(f"# Changelog v1 → v2 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n")
            f.write(f"**Account:** {args.account}\n\n")
            f.write("Changes applied after processing the onboarding call:\n\n")
            for c in changelog:
                f.write(f"- {c}\n")
            if not changelog:
                f.write("- No changes detected from onboarding transcript.\n")

        log.info(f"✅ v2 assets + changelog saved to {account_dir}/")

        # Optional: Push to Retell
        retell_id = None
        if args.retell_key:
            retell_id = push_to_retell(spec, args.retell_key)
            if retell_id:
                with open(os.path.join(account_dir, "retell_metadata.json"), "w") as f:
                    json.dump({
                        "agent_id": retell_id,
                        "deployed_at": datetime.now().isoformat(),
                        "version": "v2"
                    }, f, indent=4)

        result = {
            "status": "success",
            "account_id": args.account,
            "pipeline": "onboarding",
            "version": "v2",
            "changes_count": len(changelog),
            "retell_agent_id": retell_id,
            "outputs": {
                "memo": v2_memo_path,
                "agent_spec": v2_spec_path,
                "changelog": changelog_path
            }
        }
        print(json.dumps(result))


if __name__ == "__main__":
    main()