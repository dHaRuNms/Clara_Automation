#!/usr/bin/env python3
"""
Clara Multi-Agent – Config Generator Agent
============================================
Generates the optimized Retell LLM config using the validated memo.
Uses research context from the Researcher to tune prompt wording.
Uses Llama 3.3 70b on NVIDIA NIM.
"""

import json
import logging
from openai import OpenAI

log = logging.getLogger("clara.agent.config")

CONFIG_SYSTEM = """You are a senior voice AI engineer at Clara AI.

Your job is to generate optimized system prompts and conversation state configurations
for Clara, an AI voice receptionist for service trade businesses.

You produce configurations that:
- Are natural and conversational (not robotic)
- Handle emergencies with urgency and empathy
- Efficiently collect caller information
- Route calls correctly based on business rules
- Sound like a real, professional receptionist

Respond ONLY with valid JSON."""


def run_config_generator(memo: dict, research_notes: str, client: OpenAI, model: str) -> dict:
    """
    Generate enhanced Retell LLM config using memo + research context.
    Returns: {general_prompt_enhancement, state_suggestions, voice_tuning_notes}
    """
    company = memo.get("company_name", "the company")
    services = ", ".join(memo.get("services_supported", [])) or "general services"
    emergency_defs = memo.get("emergency_definition", [])
    log.info(f"[ConfigGen] Generating enhanced config for: {company}")

    prompt = f"""Generate an enhanced voice AI configuration for Clara AI receptionist for this company.

COMPANY MEMO:
{json.dumps(memo, indent=2)}

RESEARCHER NOTES (additional context):
{research_notes or "No additional research available."}

Your tasks:
1. Write an enhanced "general_prompt" that sounds natural and professional, includes all company specifics, sets clear behavioral constraints, handles the services: {services}
2. Suggest any state-specific prompt improvements for the conversation flow (greeting, emergency, collect_info, after_hours, wrap_up states)
3. Recommend voice tuning parameters appropriate for this business type
4. Generate a natural-sounding begin_message for Clara's opening greeting

Return EXACTLY this JSON:
{{
  "general_prompt_enhancement": "Full enhanced general prompt text here...",
  "begin_message": "Hi, thank you for calling...",
  "state_improvements": {{
    "greeting_and_identify": "Enhanced state prompt...",
    "emergency_handling": "Enhanced emergency prompt...",
    "collect_info": "Enhanced info collection prompt...",
    "after_hours": "Enhanced after-hours prompt...",
    "wrap_up": "Enhanced wrap-up prompt..."
  }},
  "voice_tuning": {{
    "responsiveness": 0.6,
    "interruption_sensitivity": 0.5,
    "voice_temperature": 0.5,
    "ambient_sound": "call-center",
    "enable_backchannel": true,
    "backchannel_words": ["yeah", "uh-huh", "okay", "I see", "got it"]
  }},
  "boosted_keywords": ["list of domain-specific words to boost STT recognition"],
  "config_notes": "Brief explanation of key config decisions made"
}}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": CONFIG_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=3000,
            response_format={"type": "json_object"}
        )
        raw = response.choices[0].message.content
        result = json.loads(raw)
        log.info(f"[ConfigGen] Enhanced config generated. Notes: {result.get('config_notes', '')[:100]}")
        return result
    except json.JSONDecodeError as e:
        log.error(f"[ConfigGen] JSON parse failed: {e}")
        return {}
    except Exception as e:
        log.error(f"[ConfigGen] API error: {e}")
        return {}
