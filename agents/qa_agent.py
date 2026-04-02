#!/usr/bin/env python3
"""
Clara Multi-Agent – QA Agent
==============================
Validates the merged memo (extracted + researcher suggestions).
Flags inconsistencies, prioritizes unknowns, scores config completeness.
Uses Llama 3.3 70b on NVIDIA NIM.
"""

import json
import logging
from openai import OpenAI

log = logging.getLogger("clara.agent.qa")

QA_SYSTEM = """You are a Quality Assurance specialist for Clara AI, an AI voice receptionist platform.

Your job is to VALIDATE a company configuration memo before it goes live as a voice agent.
You are checking for:
1. Logical consistency (e.g., emergency phone must be a real number format)
2. Critical missing fields that WILL break the voice agent
3. Ambiguous routing rules that need clarification
4. Config completeness score

Be strict. A real phone call will depend on this config being correct.
Respond ONLY with valid JSON."""

REQUIRED_CRITICAL_FIELDS = [
    "company_name",
    "business_hours",
    "services_supported",
    "emergency_definition",
    "emergency_routing_rules",
    "emergency_phone",
]

REQUIRED_IMPORTANT_FIELDS = [
    "timezone",
    "non_emergency_routing_rules",
    "call_transfer_rules",
    "after_hours_flow_summary",
]


def run_qa(memo: dict, client: OpenAI, model: str) -> dict:
    """
    Validate and score the merged memo.
    Returns: {issues, priority_unknowns, completeness_score, qa_passed, recommendations}
    """
    company = memo.get("company_name", "Unknown")
    log.info(f"[QA] Running validation for: {company}")

    # Pre-check: count critical + important fields
    critical_missing = [f for f in REQUIRED_CRITICAL_FIELDS if not memo.get(f)]
    important_missing = [f for f in REQUIRED_IMPORTANT_FIELDS if not memo.get(f)]

    total_fields = len(REQUIRED_CRITICAL_FIELDS) + len(REQUIRED_IMPORTANT_FIELDS)
    filled = total_fields - len(critical_missing) - len(important_missing)
    base_score = round((filled / total_fields) * 100)

    prompt = f"""Validate this Clara AI receptionist configuration memo for: {company}

CONFIG MEMO:
{json.dumps(memo, indent=2)}

CRITICAL fields (MUST be present for agent to work): {REQUIRED_CRITICAL_FIELDS}
IMPORTANT fields (agent works but is degraded without these): {REQUIRED_IMPORTANT_FIELDS}

PRE-CHECK RESULTS:
- Critical missing: {critical_missing}
- Important missing: {important_missing}
- Base completeness: {base_score}%

Your tasks:
1. Identify any LOGICAL INCONSISTENCIES (e.g., emergency phone format problems, contradictory routing rules)
2. Review existing questions_or_unknowns and add any new gaps you spot
3. Prioritize the top 3 most important questions needing answers
4. Give a final completeness score (0-100) considering field quality, not just presence
5. Decide if this config can be deployed: qa_passed = true if score >= 60

Return EXACTLY this JSON structure:
{{
  "issues": ["list of logical inconsistencies found"],
  "priority_unknowns": ["top 3 most critical questions needing answers"],
  "completeness_score": 85,
  "qa_passed": true,
  "recommendations": ["list of specific improvement suggestions"],
  "deploy_risk": "low|medium|high"
}}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": QA_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=1024,
            response_format={"type": "json_object"}
        )
        raw = response.choices[0].message.content
        result = json.loads(raw)
        score = result.get("completeness_score", base_score)
        passed = result.get("qa_passed", score >= 60)
        log.info(f"[QA] Score: {score}/100 | Passed: {passed} | Risk: {result.get('deploy_risk', 'unknown')}")
        return result
    except json.JSONDecodeError as e:
        log.error(f"[QA] JSON parse failed: {e}")
        return {
            "issues": ["QA agent JSON parse error"],
            "priority_unknowns": memo.get("questions_or_unknowns", [])[:3],
            "completeness_score": base_score,
            "qa_passed": base_score >= 60,
            "recommendations": [],
            "deploy_risk": "medium"
        }
    except Exception as e:
        log.error(f"[QA] API error: {e}")
        return {
            "issues": [f"QA agent error: {e}"],
            "priority_unknowns": [],
            "completeness_score": base_score,
            "qa_passed": False,
            "recommendations": [],
            "deploy_risk": "high"
        }
