#!/usr/bin/env python3
"""
Clara AI – Core Engine
======================
Gemini-powered transcript analysis + Retell-native config generation.
Extracts structured account memos from demo/onboarding transcripts and
generates production-ready Retell LLM configs with multi-state conversation flows.

Multi-Agent Mode (NVIDIA NIM):
When NVIDIA_API_KEY is set, uses DeerFlow-style 4-agent swarm:
  Extractor (Mixtral) → [Researcher + QA] (parallel) → Config Generator (Llama)
"""

import json
import os
import re
import logging
from datetime import datetime
from string import Template

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

log = logging.getLogger("clara-engine")

MULTI_AGENT_AVAILABLE = bool(os.environ.get("NVIDIA_API_KEY", ""))

# ──────────────────────────────────────────────
# Account Memo Schema
# ──────────────────────────────────────────────
MEMO_SCHEMA = {
    "account_id": "",
    "company_name": "",
    "business_hours": "",
    "timezone": "",
    "office_address": "",
    "contact_email": "",
    "contact_phone": "",
    "services_supported": [],
    "emergency_definition": [],
    "emergency_routing_rules": "",
    "emergency_phone": "",
    "non_emergency_routing_rules": "",
    "call_transfer_rules": "",
    "transfer_timeout_seconds": 30,
    "integration_constraints": "",
    "crm_system": "",
    "after_hours_flow_summary": "",
    "office_hours_flow_summary": "",
    "voicemail_message": "",
    "questions_or_unknowns": [],
    "notes": "",
    "version": "v1",
    "created_at": "",
    "updated_at": ""
}

# ──────────────────────────────────────────────
# Gemini Prompts
# ──────────────────────────────────────────────
DEMO_PROMPT = """You are an expert data extraction specialist for Clara AI, an AI voice receptionist platform for service trade businesses (electricians, plumbers, HVAC, etc).

Analyze this DEMO CALL transcript/notes and extract ALL structured information. ONLY extract what is EXPLICITLY stated. Do NOT invent or assume facts.

Return a valid JSON object with EXACTLY these fields:
{
  "company_name": "string - company name if mentioned",
  "business_hours": "string - exact hours if stated (e.g. 'Monday to Friday, 8 AM to 5 PM')",
  "timezone": "string - timezone if mentioned (e.g. 'Mountain Time', 'EST')",
  "office_address": "string - address if mentioned",
  "contact_email": "string - email if mentioned",
  "contact_phone": "string - phone number if mentioned",
  "services_supported": ["list of services the company provides"],
  "emergency_definition": ["list of what constitutes an emergency"],
  "emergency_routing_rules": "string - how emergency calls should be routed",
  "emergency_phone": "string - emergency contact phone number",
  "non_emergency_routing_rules": "string - how non-emergency calls are handled",
  "call_transfer_rules": "string - transfer timeouts, retries, fallback",
  "transfer_timeout_seconds": 30,
  "integration_constraints": "string - CRM/system integration rules",
  "crm_system": "string - CRM name if mentioned (Jobber, ServiceTitan, etc)",
  "after_hours_flow_summary": "string - after-hours call flow summary",
  "office_hours_flow_summary": "string - business hours call flow summary",
  "voicemail_message": "string - custom voicemail message if discussed",
  "questions_or_unknowns": ["list of critical missing details needing clarification"],
  "notes": "string - any other relevant details"
}

RULES:
- If info is NOT in the transcript, use empty string "" or empty list []
- Do NOT guess hours, addresses, or routing rules
- Extract EXACT wording from transcript where possible
- Flag genuinely missing critical config items in questions_or_unknowns

TRANSCRIPT:
---
$transcript
---

Respond ONLY with the JSON object. No markdown, no explanation."""

ONBOARDING_PROMPT = """You are an expert data extraction specialist for Clara AI. Process this ONBOARDING CALL transcript to update an existing account configuration.

Existing v1 account memo:
```json
$existing_memo
```

Analyze the onboarding transcript and extract ALL new or updated configuration details.

Return a JSON object with TWO keys:
{{
  "updated_fields": {{
    // ONLY fields with new/updated information. Same field names as original memo.
    // If a field was empty in v1 and now clarified, include it.
    // If unchanged, do NOT include it.
  }},
  "changelog": [
    "Human-readable description of each change",
    "Format: 'Updated <field>: <old> → <new>' or 'Added <field>: <value>'"
  ]
}}

RULES:
- ONLY include fields explicitly updated in the onboarding transcript
- Do NOT copy unchanged fields
- Clear questions_or_unknowns for items now answered
- Look for: hours, timezone, emergency definitions, routing rules, transfer rules, CRM constraints

ONBOARDING TRANSCRIPT:
---
$transcript
---

Respond ONLY with the JSON object."""


# ──────────────────────────────────────────────
# Multi-Agent Engine (DeerFlow-style, NVIDIA NIM)
# ──────────────────────────────────────────────

class ClaraMultiAgent:
    """
    DeerFlow-style multi-agent pipeline for Clara.
    Uses NVIDIA NIM models (free) via OpenAI-compatible API.
    Falls back to ClaraEngine (Gemini) if NVIDIA_API_KEY not set.
    """

    def __init__(self):
        self.nvidia_key = os.environ.get("NVIDIA_API_KEY", "")
        self.available = bool(self.nvidia_key)
        if self.available:
            log.info("[MultiAgent] NVIDIA NIM key found — Multi-Agent Mode ACTIVE")
        else:
            log.warning("[MultiAgent] No NVIDIA_API_KEY — falling back to classic Gemini mode")
        # Fallback engine
        self._classic = ClaraEngine()

    def analyze_demo(self, transcript_text: str, account_id: str = "") -> tuple:
        """
        Run multi-agent pipeline on a demo transcript.
        Returns (memo, agent_trace) — agent_trace is [] in classic mode.
        """
        if not self.available:
            log.info("[MultiAgent] Classic mode: single Gemini call")
            memo = self._classic.analyze_demo(transcript_text, account_id)
            return memo, []

        log.info(f"[MultiAgent] 🚀 Running multi-agent pipeline for: {account_id}")
        try:
            from agents.orchestrator import run_multi_agent_pipeline
            result = run_multi_agent_pipeline(transcript_text, account_id)

            memo = result.get("memo", {})
            memo["account_id"] = account_id
            memo["version"] = "v1"
            memo["created_at"] = datetime.now().isoformat()
            memo["updated_at"] = datetime.now().isoformat()

            agent_trace = result.get("agent_trace", [])
            errors = result.get("errors", [])
            if errors:
                log.warning(f"[MultiAgent] Pipeline had {len(errors)} error(s): {errors}")

            return memo, agent_trace

        except Exception as e:
            log.error(f"[MultiAgent] Pipeline failed: {e} — falling back to Gemini")
            memo = self._classic.analyze_demo(transcript_text, account_id)
            return memo, [{"agent": "fallback", "status": "error", "summary": f"Multi-agent failed: {e}"}]

    def analyze_onboarding(self, transcript_text: str, v1_memo: dict) -> tuple:
        """
        Run multi-agent pipeline on onboarding transcript with existing v1 memo.
        Returns (v2_memo, changelog, agent_trace).
        """
        if not self.available:
            v2_memo, changelog = self._classic.analyze_onboarding(transcript_text, v1_memo)
            return v2_memo, changelog, []

        log.info(f"[MultiAgent] 🔄 Onboarding pipeline for: {v1_memo.get('account_id', 'unknown')}")
        try:
            from agents.orchestrator import run_multi_agent_pipeline
            result = run_multi_agent_pipeline(transcript_text, v1_memo.get("account_id", ""), existing_memo=v1_memo)

            new_memo = result.get("memo", {})
            v2_memo = v1_memo.copy()
            v2_memo.update({k: v for k, v in new_memo.items() if v and v != [] and v != ""})
            v2_memo["version"] = "v2"
            v2_memo["updated_at"] = datetime.now().isoformat()

            changelog = [f"[Multi-Agent] {t.get('agent', '?')}: {t.get('summary', '')}" for t in result.get("agent_trace", [])]
            agent_trace = result.get("agent_trace", [])
            return v2_memo, changelog, agent_trace

        except Exception as e:
            log.error(f"[MultiAgent] Onboarding pipeline failed: {e} — falling back")
            v2_memo, changelog = self._classic.analyze_onboarding(transcript_text, v1_memo)
            return v2_memo, changelog, []

    def generate_retell_llm_config(self, memo: dict, config_enhancements: dict = None):
        """
        Generate Retell LLM config, applying multi-agent enhancements if available.
        """
        llm_config, agent_config = self._classic.generate_retell_llm_config(memo)

        if config_enhancements:
            # Apply enhanced prompts from Config Generator agent
            enhanced_general = config_enhancements.get("general_prompt_enhancement")
            if enhanced_general:
                llm_config["general_prompt"] = enhanced_general

            enhanced_begin = config_enhancements.get("begin_message")
            if enhanced_begin:
                llm_config["begin_message"] = enhanced_begin

            # Apply state-level prompt improvements
            state_improvements = config_enhancements.get("state_improvements", {})
            if state_improvements and llm_config.get("states"):
                for state in llm_config["states"]:
                    name = state["name"]
                    if name in state_improvements and state_improvements[name]:
                        state["state_prompt"] = state_improvements[name]

            # Apply voice tuning
            voice_tuning = config_enhancements.get("voice_tuning", {})
            if voice_tuning:
                agent_config["responsiveness"] = voice_tuning.get("responsiveness", agent_config["responsiveness"])
                agent_config["interruption_sensitivity"] = voice_tuning.get("interruption_sensitivity", agent_config["interruption_sensitivity"])
                agent_config["voice_temperature"] = voice_tuning.get("voice_temperature", agent_config["voice_temperature"])
                agent_config["enable_backchannel"] = voice_tuning.get("enable_backchannel", True)
                if voice_tuning.get("backchannel_words"):
                    agent_config["backchannel_words"] = voice_tuning["backchannel_words"]

            # Apply boosted keywords
            boosted = config_enhancements.get("boosted_keywords", [])
            if boosted:
                existing_boosted = agent_config.get("boosted_keywords", [])
                agent_config["boosted_keywords"] = list(dict.fromkeys(existing_boosted + boosted))[:15]

            log.info("[MultiAgent] Applied config enhancements from Config Generator agent")

        return llm_config, agent_config

    def save_outputs(self, memo, changelog=None, agent_trace=None, config_enhancements=None, output_dir="outputs/accounts"):
        """Save memo + enhanced Retell configs + agent trace to disk."""
        account_id = memo.get("account_id", "unknown")
        version = memo.get("version", "v1")
        account_dir = os.path.join(output_dir, account_id)
        os.makedirs(account_dir, exist_ok=True)

        # Save memo
        memo_path = os.path.join(account_dir, f"{version}_memo.json")
        with open(memo_path, "w") as f:
            json.dump(memo, f, indent=4)

        # Generate enhanced Retell configs
        llm_config, agent_config = self.generate_retell_llm_config(memo, config_enhancements)

        llm_path = os.path.join(account_dir, f"{version}_retell_llm.json")
        with open(llm_path, "w") as f:
            json.dump(llm_config, f, indent=4)

        agent_path = os.path.join(account_dir, f"{version}_retell_agent.json")
        with open(agent_path, "w") as f:
            json.dump(agent_config, f, indent=4)

        # Save agent trace
        if agent_trace:
            trace_path = os.path.join(account_dir, f"{version}_agent_trace.json")
            with open(trace_path, "w") as f:
                json.dump({"account_id": account_id, "version": version, "trace": agent_trace, "generated_at": datetime.now().isoformat()}, f, indent=4)
            log.info(f"[MultiAgent] Saved agent trace → {trace_path}")

        # Save changelog
        if changelog:
            cl_path = os.path.join(account_dir, "changelog.md")
            with open(cl_path, "w") as f:
                f.write(f"# Changelog v1 → v2 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n")
                f.write(f"**Account:** {account_id}\n\n")
                for c in changelog:
                    f.write(f"- {c}\n")
            log.info(f"Saved {cl_path}")

        return {
            "memo": memo_path,
            "llm_config": llm_path,
            "agent_config": agent_path,
            "changelog": os.path.join(account_dir, "changelog.md") if changelog else None,
            "agent_trace": os.path.join(account_dir, f"{version}_agent_trace.json") if agent_trace else None,
        }


class ClaraEngine:
    """Core engine for transcript analysis and Retell config generation."""

    def __init__(self, gemini_key=None):
        self.gemini_key = gemini_key or os.environ.get("GEMINI_API_KEY", "")
        if genai and self.gemini_key:
            self.client = genai.Client(api_key=self.gemini_key)
            log.info("Gemini client initialized.")
        else:
            self.client = None
            log.warning("No Gemini client – will use rule-based fallback.")

    def _call_gemini(self, prompt):
        """Call Gemini Flash API."""
        if not self.client:
            return None
        try:
            response = self.client.models.generate_content(
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
        except json.JSONDecodeError:
            # Try to extract JSON from response
            try:
                match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if match:
                    return json.loads(match.group())
            except Exception:
                pass
            log.error("Failed to parse Gemini response as JSON.")
            return None
        except Exception as e:
            log.error(f"Gemini API error: {e}")
            return None

    def analyze_demo(self, transcript_text, account_id=""):
        """Analyze a demo call transcript → v1 account memo."""
        log.info(f"Analyzing demo transcript for account: {account_id}")

        prompt = Template(DEMO_PROMPT).substitute(transcript=transcript_text)
        result = self._call_gemini(prompt)

        memo = MEMO_SCHEMA.copy()
        memo["account_id"] = account_id
        memo["version"] = "v1"
        memo["created_at"] = datetime.now().isoformat()
        memo["updated_at"] = datetime.now().isoformat()

        if result:
            for key in memo:
                if key in result and result[key]:
                    memo[key] = result[key]
        else:
            log.warning("Gemini failed, using rule-based extraction.")
            memo = self._extract_rules(transcript_text, memo)

        return memo

    def analyze_onboarding(self, transcript_text, v1_memo):
        """Analyze onboarding transcript → v2 memo + changelog."""
        log.info(f"Analyzing onboarding for account: {v1_memo.get('account_id', 'unknown')}")

        prompt = Template(ONBOARDING_PROMPT).substitute(
            transcript=transcript_text,
            existing_memo=json.dumps(v1_memo, indent=2)
        )
        result = self._call_gemini(prompt)

        v2_memo = v1_memo.copy()
        v2_memo["version"] = "v2"
        v2_memo["updated_at"] = datetime.now().isoformat()

        if result:
            updated = result.get("updated_fields", {})
            changelog = result.get("changelog", [])
            for key, value in updated.items():
                if key in v2_memo:
                    v2_memo[key] = value
            # Clear answered unknowns
            if updated:
                remaining = [q for q in v2_memo.get("questions_or_unknowns", [])
                             if not any(f.lower() in q.lower() for f in updated.keys())]
                v2_memo["questions_or_unknowns"] = remaining
        else:
            log.warning("Gemini failed, using rule-based onboarding extraction.")
            v2_memo, changelog = self._extract_onboarding_rules(transcript_text, v2_memo)

        return v2_memo, changelog

    def generate_retell_llm_config(self, memo):
        """Generate a Retell LLM config with multi-state conversation flow."""
        company = memo.get("company_name", "the company")
        hours = memo.get("business_hours", "standard business hours")
        tz = memo.get("timezone", "")
        services = ", ".join(memo.get("services_supported", [])) or "general services"
        emergency_defs = memo.get("emergency_definition", [])
        emergency_list = ", ".join(emergency_defs) if emergency_defs else "any safety-critical situation"
        emergency_phone = memo.get("emergency_phone", memo.get("contact_phone", ""))
        emergency_route = memo.get("emergency_routing_rules", "Route to on-call staff.")
        non_emergency = memo.get("non_emergency_routing_rules", "Collect details, confirm callback.")
        transfer_timeout = memo.get("transfer_timeout_seconds", 30)
        integration = memo.get("integration_constraints", "")
        crm = memo.get("crm_system", "")
        address = memo.get("office_address", "")

        general_prompt = f"""# Persona
You are Clara, a friendly and professional AI receptionist for {company}.
Your tone is warm, helpful, efficient, and precise. You speak naturally and conversationally.
You never mention that you are an AI, artificial intelligence, or automation.

# Company Info
- Company: {company}
- Business Hours: {hours}{f' ({tz})' if tz else ''}
- Services: {services}
{f'- Address: {address}' if address else ''}
{f'- CRM System: {crm}' if crm else ''}

# Critical Constraints
- You MUST collect the caller's name and phone number on EVERY call.
- Do NOT mention "AI", "artificial intelligence", "function calls", or "automation".
- Do NOT diagnose technical problems — only collect information and route.
- Keep conversations focused and efficient.
{f'- {integration}' if integration else ''}
- Always confirm collected information before ending the call.
- Be empathetic during emergencies.
- Never leave the caller in silence for more than 10 seconds.

# Emergency Info
- Emergency triggers: {emergency_list}
- Emergency routing: {emergency_route}"""

        begin_message = f"Hi, thank you for calling {company}! This is Clara. How can I help you today?"

        # Build multi-state conversation flow
        states = [
            {
                "name": "greeting_and_identify",
                "state_prompt": f"""You just greeted the caller. Listen carefully to understand their need.
Ask clarifying questions if needed to determine:
1. Is this an emergency? (triggers: {emergency_list})
2. What service do they need?
3. Is this during or outside business hours ({hours})?

If it's an emergency, transition to emergency_handling immediately.
If it's a routine call during business hours, transition to collect_info.
If it's after hours and non-emergency, transition to after_hours.""",
                "edges": [
                    {
                        "destination_state_name": "emergency_handling",
                        "description": "Caller has an emergency situation"
                    },
                    {
                        "destination_state_name": "collect_info",
                        "description": "Routine call during business hours"
                    },
                    {
                        "destination_state_name": "after_hours",
                        "description": "Non-emergency call outside business hours"
                    }
                ],
                "tools": []
            },
            {
                "name": "emergency_handling",
                "state_prompt": f"""This is an EMERGENCY call. Act with urgency and empathy.
1. Say: "I understand this is urgent. Let me help you right away."
2. Collect immediately: caller's name, phone number, and address/location.
3. Confirm the nature of the emergency.
4. Say: "Let me connect you to our emergency team right now."
5. Use the transfer_call tool to connect them to {emergency_phone if emergency_phone else 'the emergency number'}.
6. If transfer fails, say: "I'm sorry I wasn't able to connect you directly. I've logged this as an urgent emergency and someone will contact you as soon as possible."
7. Then transition to wrap_up.""",
                "edges": [
                    {
                        "destination_state_name": "wrap_up",
                        "description": "Emergency has been handled or transfer attempted"
                    }
                ],
                "tools": self._build_transfer_tool(emergency_phone) if emergency_phone else []
            },
            {
                "name": "collect_info",
                "state_prompt": f"""Collect the caller's information for their service request.
1. Ask: "May I have your name and the best number to reach you?"
2. Ask about the service they need from: {services}
3. Ask about preferred timing/scheduling if applicable.
4. Summarize what you've collected.
5. Say: "Let me connect you with the right team member."
6. Use transfer_call to route them, or transition to wrap_up if no transfer needed.""",
                "edges": [
                    {
                        "destination_state_name": "wrap_up",
                        "description": "Information collected, ready to wrap up"
                    }
                ],
                "tools": self._build_transfer_tool(memo.get("contact_phone", "")) if memo.get("contact_phone") else []
            },
            {
                "name": "after_hours",
                "state_prompt": f"""The caller is reaching us outside business hours ({hours}).
1. Inform them: "I should let you know we're currently outside our regular business hours of {hours}."
2. Collect: caller's name, phone number, and a brief description of their need.
3. {non_emergency}
4. Say: "I've noted your details. A team member will reach out during our next business day."
5. Transition to wrap_up.""",
                "edges": [
                    {
                        "destination_state_name": "wrap_up",
                        "description": "After-hours message taken"
                    }
                ],
                "tools": []
            },
            {
                "name": "wrap_up",
                "state_prompt": """Wrap up the call professionally.
1. Ask: "Is there anything else I can help you with today?"
2. If yes, address their question or transition back to the appropriate state.
3. If no, say: "Thank you for calling! Have a wonderful day."
4. Use the end_call tool to end the call.""",
                "edges": [
                    {
                        "destination_state_name": "greeting_and_identify",
                        "description": "Caller has another question"
                    }
                ],
                "tools": []
            }
        ]

        # Post-call analysis
        post_call_analysis = [
            {
                "type": "string",
                "name": "caller_name",
                "description": "The full name of the caller.",
                "examples": ["John Smith", "Sarah Johnson"]
            },
            {
                "type": "string",
                "name": "caller_phone",
                "description": "The phone number provided by the caller.",
                "examples": ["403-555-1234", "555-0199"]
            },
            {
                "type": "string",
                "name": "call_type",
                "description": "The type of call: emergency, service_request, inquiry, or complaint.",
                "examples": ["emergency", "service_request", "inquiry"]
            },
            {
                "type": "string",
                "name": "service_requested",
                "description": "The specific service the caller needs.",
                "examples": ["electrical repair", "inspection", "emergency power outage"]
            },
            {
                "type": "string",
                "name": "urgency_level",
                "description": "The urgency: critical, high, medium, or low.",
                "examples": ["critical", "high", "medium", "low"]
            },
            {
                "type": "string",
                "name": "caller_address",
                "description": "The address or location provided by the caller.",
                "examples": ["123 Main Street", "Downtown office"]
            },
            {
                "type": "string",
                "name": "action_taken",
                "description": "What action was taken: transferred, message_taken, appointment_scheduled, information_provided.",
                "examples": ["transferred", "message_taken", "appointment_scheduled"]
            },
            {
                "type": "string",
                "name": "preferred_schedule",
                "description": "When the caller is available or prefers to be contacted back, e.g. 'tomorrow morning', 'after 3pm', 'weekdays only'.",
                "examples": ["tomorrow morning", "after 3pm", "any weekday"]
            },
            {
                "type": "string",
                "name": "call_summary",
                "description": "A 1-2 sentence summary of the caller's problem or request.",
                "examples": ["Caller reported a power outage in their basement and needs emergency service.", "Customer wants to schedule an electrical inspection for their new home."]
            }
        ]

        llm_config = {
            "model": "gpt-4.1",
            "model_temperature": 0.3,
            "tool_call_strict_mode": True,
            "start_speaker": "agent",
            "begin_message": begin_message,
            "general_prompt": general_prompt,
            "general_tools": [
                {
                    "type": "end_call",
                    "name": "end_call",
                    "description": "End the call with the caller."
                }
            ],
            "states": states,
            "starting_state": "greeting_and_identify",
            "default_dynamic_variables": {
                "company_name": company,
                "business_hours": hours,
                "timezone": tz
            }
        }

        agent_config = {
            "agent_name": f"Clara AI – {company}",
            "voice_id": "retell-Cimo",
            "voice_temperature": 0.5,
            "voice_speed": 1,
            "enable_dynamic_voice_speed": False,
            "enable_dynamic_responsiveness": False,
            "volume": 1,
            "responsiveness": 0.6,
            "interruption_sensitivity": 0.5,
            "enable_backchannel": True,
            "backchannel_frequency": 0.5,
            "backchannel_words": ["yeah", "uh-huh", "okay"],
            "reminder_trigger_ms": 15000,
            "reminder_max_count": 2,
            "ambient_sound": "call-center",
            "ambient_sound_volume": 0.2,
            "language": "en-US",
            "normalize_for_speech": True,
            "end_call_after_silence_ms": 30000,
            "max_call_duration_ms": 1800000,
            "enable_voicemail_detection": True,
            "voicemail_message": memo.get("voicemail_message", "") or f"Hi, you've reached {company}. We're sorry we missed your call. Please leave a message and we'll get back to you during our next business day.",
            "voicemail_detection_timeout_ms": 30000,
            "post_call_analysis_data": post_call_analysis,
            "post_call_analysis_model": "gpt-4.1",
            "analysis_successful_prompt": "The agent successfully collected caller information and either transferred the call, took a message, or resolved the inquiry.",
            "analysis_summary_prompt": "Summarize the call outcome: who called, what they needed, and what action was taken.",
            "analysis_user_sentiment_prompt": "Rate the caller's sentiment from 1-5 (1=very negative, 5=very positive) based on their tone throughout the call.",
            "stt_mode": "fast",
            "denoising_mode": "noise-cancellation",
            "boosted_keywords": [company] + memo.get("services_supported", [])[:5],
        }

        return llm_config, agent_config

    def _build_transfer_tool(self, phone_number):
        """Build a transfer_call tool for Retell."""
        if not phone_number:
            return []
        # Clean phone number – ensure E.164 format
        clean = re.sub(r'[^\d+]', '', phone_number)
        if not clean.startswith('+'):
            if len(clean) == 10:
                clean = '+1' + clean
            elif len(clean) == 11 and clean.startswith('1'):
                clean = '+' + clean

        return [
            {
                "type": "transfer_call",
                "name": "transfer_to_team",
                "description": "Transfer the caller to the team member or on-call staff.",
                "transfer_destination": {
                    "type": "predefined",
                    "number": clean,
                    "ignore_e164_validation": True
                },
                "transfer_option": {
                    "type": "cold_transfer",
                    "show_transferee_as_caller": False
                }
            }
        ]

    def _extract_rules(self, text, memo):
        """Rule-based fallback extraction."""
        # Company name
        patterns = [
            r"(?:Company|Business|company):\s*(.+?)(?:\n|$)",
            r"(?:for|called|at)\s+([A-Z][A-Za-z'\s]+(?:Solutions|Electric|Services|HVAC|Plumbing))",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                memo["company_name"] = m.group(1).strip()
                break

        # Email
        m = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
        if m:
            memo["contact_email"] = m.group()

        # Phone
        m = re.search(r'(\d{3}[-.]?\d{3}[-.]?\d{4})', text)
        if m:
            memo["contact_phone"] = m.group(1)
            memo["emergency_phone"] = m.group(1)

        # Services
        service_keywords = ["electrical", "plumbing", "hvac", "fire protection",
                            "sprinkler", "alarm", "inspection", "maintenance", "repair"]
        memo["services_supported"] = [s.title() for s in service_keywords if s in text.lower()]

        # CRM
        for crm in ["jobber", "servicetitan", "housecall pro", "servicetrade"]:
            if crm.lower() in text.lower():
                memo["crm_system"] = crm.title()
                break

        # Unknowns
        unknowns = []
        if not memo["business_hours"]:
            unknowns.append("What are the exact business hours?")
        if not memo["emergency_definition"]:
            unknowns.append("What constitutes an emergency?")
        if not memo["emergency_routing_rules"]:
            unknowns.append("How should emergency calls be routed?")
        memo["questions_or_unknowns"] = unknowns

        return memo

    def _extract_onboarding_rules(self, text, memo):
        """Rule-based fallback for onboarding."""
        changelog = []

        # Business hours
        m = re.search(r'(Monday\s*(?:to|through)\s*\w+),?\s*(\d+\s*(?:AM|am)\s*(?:to|-)\s*\d+\s*(?:PM|pm))', text, re.IGNORECASE)
        if m:
            hours = f"{m.group(1)}, {m.group(2)}"
            tz = re.search(r'(Mountain|Pacific|Eastern|Central)\s*Time', text, re.IGNORECASE)
            if tz:
                hours += f", {tz.group(1)} Time"
                memo["timezone"] = f"{tz.group(1)} Time"
            memo["business_hours"] = hours
            changelog.append(f"Updated business_hours: {hours}")

        # Emergency definitions
        emergency_keywords = ["power outage", "sparking", "exposed wires", "fire alarm",
                              "gas leak", "flooding", "electrical fire"]
        found = [e.title() for e in emergency_keywords if e in text.lower()]
        if found:
            memo["emergency_definition"] = found
            changelog.append(f"Added emergency_definition: {', '.join(found)}")

        # Emergency routing
        m = re.search(r'(?:route|call|contact).*?(\d{3}[-.]?\d{3}[-.]?\d{4})', text, re.IGNORECASE)
        if m:
            memo["emergency_phone"] = m.group(1)
            memo["emergency_routing_rules"] = f"Route to {m.group(1)}."
            changelog.append(f"Set emergency routing: {m.group(1)}")

        # Transfer rules
        m = re.search(r'(?:transfer\s+fails?).*?(\d+)\s*seconds?.*?(voicemail|fallback|dispatch)', text, re.IGNORECASE)
        if m:
            memo["transfer_timeout_seconds"] = int(m.group(1))
            memo["call_transfer_rules"] = f"Fallback to {m.group(2)} after {m.group(1)} seconds."
            changelog.append(f"Set transfer rules: fallback to {m.group(2)} after {m.group(1)}s")

        # Integration constraints
        m = re.search(r'never\s+create.*?(?:in|on)\s+(\w+)\s+without', text, re.IGNORECASE)
        if m:
            memo["integration_constraints"] = f"Never create jobs automatically in {m.group(1)} without approval."
            changelog.append(f"Set integration constraint: no auto-create in {m.group(1)}")

        memo["questions_or_unknowns"] = []
        return memo, changelog

    def save_outputs(self, memo, changelog=None, output_dir="outputs/accounts"):
        """Save memo, agent spec, and changelog to disk."""
        account_id = memo.get("account_id", "unknown")
        version = memo.get("version", "v1")
        account_dir = os.path.join(output_dir, account_id)
        os.makedirs(account_dir, exist_ok=True)

        # Save memo
        memo_path = os.path.join(account_dir, f"{version}_memo.json")
        with open(memo_path, "w") as f:
            json.dump(memo, f, indent=4)
        log.info(f"Saved {memo_path}")

        # Generate and save Retell config
        llm_config, agent_config = self.generate_retell_llm_config(memo)

        llm_path = os.path.join(account_dir, f"{version}_retell_llm.json")
        with open(llm_path, "w") as f:
            json.dump(llm_config, f, indent=4)
        log.info(f"Saved {llm_path}")

        agent_path = os.path.join(account_dir, f"{version}_retell_agent.json")
        with open(agent_path, "w") as f:
            json.dump(agent_config, f, indent=4)
        log.info(f"Saved {agent_path}")

        # Save changelog
        if changelog:
            cl_path = os.path.join(account_dir, "changelog.md")
            with open(cl_path, "w") as f:
                f.write(f"# Changelog v1 → v2 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n")
                f.write(f"**Account:** {account_id}\n\n")
                for c in changelog:
                    f.write(f"- {c}\n")
            log.info(f"Saved {cl_path}")

        return {
            "memo": memo_path,
            "llm_config": llm_path,
            "agent_config": agent_path,
            "changelog": os.path.join(account_dir, "changelog.md") if changelog else None
        }
