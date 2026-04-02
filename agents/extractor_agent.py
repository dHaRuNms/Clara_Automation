#!/usr/bin/env python3
"""
Clara Multi-Agent – Extractor Agent
=====================================
Specialist sub-agent that pulls structured JSON fields from a call transcript.
Uses Mixtral on NVIDIA NIM (great at structured JSON extraction).
"""

import json
import logging
from openai import OpenAI

log = logging.getLogger("clara.agent.extractor")

EXTRACTOR_SYSTEM = """You are a precision data extraction engine for Clara AI, an AI receptionist platform for service trade businesses.

Your ONLY job is to extract structured data from a call transcript into the exact JSON schema provided.
Rules:
- Extract ONLY what is EXPLICITLY stated in the transcript.
- Do NOT invent, assume, or infer data that is not present.
- Use empty string "" or empty list [] for missing fields.
- Preserve exact wording where possible.
- Be especially precise about phone numbers, emails, and business hours.
- Respond ONLY with valid JSON. No markdown, no explanation."""

EXTRACTION_SCHEMA = {
    "company_name": "string",
    "business_hours": "string",
    "timezone": "string",
    "office_address": "string",
    "contact_email": "string",
    "contact_phone": "string",
    "services_supported": ["list of services"],
    "emergency_definition": ["list of emergency triggers"],
    "emergency_routing_rules": "string",
    "emergency_phone": "string",
    "non_emergency_routing_rules": "string",
    "call_transfer_rules": "string",
    "transfer_timeout_seconds": 30,
    "integration_constraints": "string",
    "crm_system": "string",
    "after_hours_flow_summary": "string",
    "office_hours_flow_summary": "string",
    "voicemail_message": "string",
    "questions_or_unknowns": ["list of missing/unclear items"],
    "notes": "string"
}


def run_extractor(transcript: str, client: OpenAI, model: str) -> dict:
    """
    Extract structured fields from transcript.
    Returns a dict matching EXTRACTION_SCHEMA.
    """
    log.info(f"[Extractor] Running extraction with model: {model}")

    prompt = f"""Extract ALL structured information from this call transcript into the JSON schema below.

SCHEMA (return exactly these fields):
{json.dumps(EXTRACTION_SCHEMA, indent=2)}

TRANSCRIPT:
---
{transcript}
---

Respond ONLY with the populated JSON object."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXTRACTOR_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            temperature=0.05,
            max_tokens=2048,
            response_format={"type": "json_object"}
        )
        raw = response.choices[0].message.content
        result = json.loads(raw)
        log.info(f"[Extractor] Extraction complete. Fields found: {sum(1 for v in result.values() if v)}")
        return result
    except json.JSONDecodeError as e:
        log.error(f"[Extractor] JSON parse failed: {e}. Raw: {raw[:200]}")
        return {}
    except Exception as e:
        log.error(f"[Extractor] API error: {e}")
        return {}
