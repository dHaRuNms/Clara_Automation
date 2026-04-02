#!/usr/bin/env python3
"""
Clara Multi-Agent – Researcher Agent
======================================
Specialist sub-agent that fills data gaps from the Extractor.
Uses Llama 3.1 405b on NVIDIA NIM (best for research + reasoning).

Strategy:
1. Identify what's MISSING from the extracted memo.
2. Use web search (Tavily) if available to look up company public info.
3. Apply industry-pattern knowledge for service trade businesses.
4. Return filled-in fields + research notes.
"""

import json
import logging
from openai import OpenAI

log = logging.getLogger("clara.agent.researcher")

RESEARCHER_SYSTEM = """You are a senior research analyst for Clara AI, an AI receptionist platform.

Your job is to help fill in MISSING configuration data for a service trade business (electricians, plumbers, HVAC, fire protection, etc.).

You have two capabilities:
1. Industry Knowledge: You know common patterns for service trade businesses (typical emergency types, CRM systems, routing patterns).
2. Reasoning: Given a company name and services, you can make EDUCATED suggestions for missing fields.

IMPORTANT RULES:
- Clearly mark any suggested data as "suggested" vs "verified".
- Only fill in fields that are MISSING (empty string or empty list) in the extracted memo.
- Use your knowledge of service trade industry patterns to fill gaps.
- Be specific and practical — these configs go live in a voice AI.
- Respond ONLY with valid JSON."""

INDUSTRY_PATTERNS = """
SERVICE TRADE INDUSTRY PATTERNS:
- Electricians: Emergencies = power outages, sparking wires, electrical fires, no power
- Plumbers: Emergencies = burst pipes, flooding, sewage backup, no water
- HVAC: Emergencies = no heat in winter, gas leaks, complete system failure
- Fire Protection: Emergencies = alarm triggered, sprinkler failure, CO alarm
- General: CRM systems commonly used = Jobber, ServiceTitan, Housecall Pro, ServiceTrade
- Transfer timeout industry standard = 30 seconds, fallback to voicemail
- After-hours: Always take name + phone + brief description, promise callback next business day
"""


def run_researcher(transcript: str, extracted_memo: dict, client: OpenAI, model: str) -> dict:
    """
    Research and fill gaps in the extracted memo.
    Returns a dict with suggested/filled fields and research_notes.
    """
    company = extracted_memo.get("company_name", "Unknown Company")
    services = extracted_memo.get("services_supported", [])
    log.info(f"[Researcher] Researching gaps for: {company} | Services: {services}")

    # Identify missing fields (empty str, empty list, or 0)
    missing_fields = []
    for key, val in extracted_memo.items():
        if key in ("version", "created_at", "updated_at", "account_id", "transfer_timeout_seconds", "notes"):
            continue
        if not val or val == "" or val == []:
            missing_fields.append(key)

    if not missing_fields:
        log.info("[Researcher] No missing fields — returning empty suggestions.")
        return {"suggested_fields": {}, "research_notes": "All fields already extracted from transcript."}

    log.info(f"[Researcher] Missing fields to research: {missing_fields}")

    prompt = f"""A call transcript extraction produced partial information about a service trade company.
Your job is to intelligently fill in the MISSING fields using industry knowledge.

COMPANY: {company}
SERVICES: {json.dumps(services)}

ALREADY EXTRACTED (do NOT re-extract these):
{json.dumps({k: v for k, v in extracted_memo.items() if k not in missing_fields}, indent=2)}

FIELDS THAT NEED TO BE FILLED:
{json.dumps(missing_fields)}

{INDUSTRY_PATTERNS}

ORIGINAL TRANSCRIPT (for context):
---
{transcript[:2000]}  
---

Instructions:
1. For each missing field, provide a SUGGESTED value based on industry patterns and the company context.
2. Prefix uncertain suggestions with "[SUGGESTED] ".
3. Return JSON with exactly two keys:
   - "suggested_fields": object with suggested values for missing fields only
   - "research_notes": string summarizing what you inferred and why

Respond ONLY with valid JSON."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": RESEARCHER_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2048,
            response_format={"type": "json_object"}
        )
        raw = response.choices[0].message.content
        result = json.loads(raw)
        suggested = result.get("suggested_fields", {})
        log.info(f"[Researcher] Suggested {len(suggested)} fields. Notes: {result.get('research_notes', '')[:100]}")
        return result
    except json.JSONDecodeError as e:
        log.error(f"[Researcher] JSON parse failed: {e}")
        return {"suggested_fields": {}, "research_notes": "Research failed — JSON parse error."}
    except Exception as e:
        log.error(f"[Researcher] API error: {e}")
        return {"suggested_fields": {}, "research_notes": f"Research failed: {e}"}
