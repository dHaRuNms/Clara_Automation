#!/usr/bin/env python3
"""
Clara Multi-Agent – Orchestrator
===================================
DeerFlow-style LangGraph StateGraph that coordinates all 4 sub-agents.

Flow:
  START → extractor_node → [researcher_node ‖ qa_node] (parallel) → config_node → END

Each node runs its specialist agent and merges results into shared AgentState.
"""

import os
import json
import logging
import time
from datetime import datetime
from typing import TypedDict, Annotated
import operator
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from agents.extractor_agent import run_extractor
from agents.researcher_agent import run_researcher
from agents.qa_agent import run_qa
from agents.config_agent import run_config_generator

log = logging.getLogger("clara.orchestrator")

# ─────────────────────────────────────────────
# NVIDIA NIM Client Factory
# ─────────────────────────────────────────────

def get_nvidia_client() -> OpenAI:
    """Create an OpenAI client pointed at NVIDIA NIM."""
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    base_url = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    if not api_key:
        raise EnvironmentError("NVIDIA_API_KEY not set in environment.")
    return OpenAI(api_key=api_key, base_url=base_url)


# ─────────────────────────────────────────────
# Model config
# ─────────────────────────────────────────────

def get_models() -> dict:
    return {
        "extractor": os.environ.get("NVIDIA_EXTRACTOR_MODEL", "mistralai/mixtral-8x22b-instruct-v0.1"),
        "researcher": os.environ.get("NVIDIA_RESEARCH_MODEL", "meta/llama-3.1-405b-instruct"),
        "qa": os.environ.get("NVIDIA_DEFAULT_MODEL", "meta/llama-3.3-70b-instruct"),
        "config": os.environ.get("NVIDIA_DEFAULT_MODEL", "meta/llama-3.3-70b-instruct"),
    }


# ─────────────────────────────────────────────
# Agent State
# ─────────────────────────────────────────────

class AgentState(TypedDict):
    transcript: str
    account_id: str
    extracted_memo: dict
    research_result: dict
    qa_result: dict
    config_result: dict
    merged_memo: dict
    agent_trace: list  # list of {agent, duration_ms, summary}
    errors: list


# ─────────────────────────────────────────────
# Node Functions
# ─────────────────────────────────────────────

def extractor_node(state: AgentState, client: OpenAI, models: dict) -> dict:
    """Run the Extractor sub-agent."""
    start = time.time()
    log.info("[Orchestrator] → Extractor node starting")
    try:
        result = run_extractor(state["transcript"], client, models["extractor"])
        duration_ms = int((time.time() - start) * 1000)
        trace_entry = {
            "agent": "extractor",
            "model": models["extractor"],
            "duration_ms": duration_ms,
            "summary": f"Extracted {sum(1 for v in result.values() if v)} non-empty fields",
            "status": "success"
        }
        return {"extracted_memo": result, "agent_trace": [trace_entry]}
    except Exception as e:
        log.error(f"[Orchestrator] Extractor failed: {e}")
        return {
            "extracted_memo": {},
            "errors": [f"extractor: {e}"],
            "agent_trace": [{"agent": "extractor", "status": "error", "summary": str(e)}]
        }


def researcher_node(state: AgentState, client: OpenAI, models: dict) -> dict:
    """Run the Researcher sub-agent."""
    start = time.time()
    log.info("[Orchestrator] ‖ Researcher node starting (parallel)")
    try:
        result = run_researcher(state["transcript"], state["extracted_memo"], client, models["researcher"])
        duration_ms = int((time.time() - start) * 1000)
        suggested_count = len(result.get("suggested_fields", {}))
        trace_entry = {
            "agent": "researcher",
            "model": models["researcher"],
            "duration_ms": duration_ms,
            "summary": f"Suggested {suggested_count} gap-fills. {result.get('research_notes', '')[:120]}",
            "status": "success"
        }
        return {"research_result": result, "agent_trace": [trace_entry]}
    except Exception as e:
        log.error(f"[Orchestrator] Researcher failed: {e}")
        return {
            "research_result": {"suggested_fields": {}, "research_notes": str(e)},
            "errors": [f"researcher: {e}"],
            "agent_trace": [{"agent": "researcher", "status": "error", "summary": str(e)}]
        }


def qa_node(state: AgentState, client: OpenAI, models: dict) -> dict:
    """Run the QA sub-agent."""
    start = time.time()
    log.info("[Orchestrator] ‖ QA node starting (parallel)")
    # QA runs against extracted + any researcher suggestions merged in
    merged = _merge_extracted_and_research(state["extracted_memo"], state.get("research_result", {}))
    try:
        result = run_qa(merged, client, models["qa"])
        duration_ms = int((time.time() - start) * 1000)
        score = result.get("completeness_score", "?")
        trace_entry = {
            "agent": "qa",
            "model": models["qa"],
            "duration_ms": duration_ms,
            "summary": f"Score: {score}/100 | Deploy risk: {result.get('deploy_risk', '?')} | Issues: {len(result.get('issues', []))}",
            "status": "success" if result.get("qa_passed") else "warning"
        }
        return {"qa_result": result, "agent_trace": [trace_entry]}
    except Exception as e:
        log.error(f"[Orchestrator] QA failed: {e}")
        return {
            "qa_result": {"completeness_score": 0, "qa_passed": False, "issues": [str(e)]},
            "errors": [f"qa: {e}"],
            "agent_trace": [{"agent": "qa", "status": "error", "summary": str(e)}]
        }


def config_node(state: AgentState, client: OpenAI, models: dict) -> dict:
    """Run the Config Generator sub-agent."""
    start = time.time()
    log.info("[Orchestrator] → Config Generator node starting")
    merged = _merge_extracted_and_research(state["extracted_memo"], state.get("research_result", {}))
    research_notes = state.get("research_result", {}).get("research_notes", "")
    try:
        result = run_config_generator(merged, research_notes, client, models["config"])
        duration_ms = int((time.time() - start) * 1000)
        trace_entry = {
            "agent": "config_generator",
            "model": models["config"],
            "duration_ms": duration_ms,
            "summary": result.get("config_notes", "Config generated")[:150],
            "status": "success"
        }
        return {"config_result": result, "merged_memo": merged, "agent_trace": [trace_entry]}
    except Exception as e:
        log.error(f"[Orchestrator] Config generator failed: {e}")
        return {
            "config_result": {},
            "merged_memo": merged,
            "errors": [f"config_generator: {e}"],
            "agent_trace": [{"agent": "config_generator", "status": "error", "summary": str(e)}]
        }


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

def _merge_extracted_and_research(extracted: dict, research_result: dict) -> dict:
    """Merge extractor output with researcher suggestions (extracted wins for non-empty fields)."""
    merged = dict(extracted)  # copy
    suggested = research_result.get("suggested_fields", {})
    for key, val in suggested.items():
        if key not in merged or not merged[key] or merged[key] in ("", []):
            merged[key] = val
    return merged


# ─────────────────────────────────────────────
# Main Orchestrator
# ─────────────────────────────────────────────

def run_multi_agent_pipeline(transcript: str, account_id: str = "", existing_memo: dict = None) -> dict:
    """
    DeerFlow-style multi-agent pipeline for Clara.
    
    Flow:
      1. Extractor → structured JSON from transcript
      2. Researcher + QA run IN PARALLEL (ThreadPoolExecutor)
      3. Config Generator → enhanced Retell config

    Returns:
      {
        "memo": merged_and_validated_memo,
        "qa_result": {...},
        "config_enhancements": {...},
        "agent_trace": [...],
        "errors": [...],
        "pipeline_duration_ms": int
      }
    """
    pipeline_start = time.time()
    log.info(f"[Orchestrator] 🚀 Multi-agent pipeline starting | Account: {account_id}")

    try:
        client = get_nvidia_client()
    except EnvironmentError as e:
        log.error(f"[Orchestrator] NVIDIA client init failed: {e}")
        return {"error": str(e), "agent_trace": [], "errors": [str(e)]}

    models = get_models()
    log.info(f"[Orchestrator] Models: {models}")

    # Initialize state
    state: AgentState = {
        "transcript": transcript,
        "account_id": account_id,
        "extracted_memo": existing_memo or {},
        "research_result": {},
        "qa_result": {},
        "config_result": {},
        "merged_memo": {},
        "agent_trace": [],
        "errors": []
    }

    # ── Step 1: Extractor ──
    extractor_output = extractor_node(state, client, models)
    state["extracted_memo"] = extractor_output.get("extracted_memo", {})
    state["agent_trace"] += extractor_output.get("agent_trace", [])
    state["errors"] += extractor_output.get("errors", [])

    # ── Step 2: Researcher + QA in PARALLEL ──
    log.info("[Orchestrator] Running Researcher + QA in parallel...")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(researcher_node, state, client, models): "researcher",
            executor.submit(qa_node, state, client, models): "qa",
        }
        for future in as_completed(futures):
            agent_name = futures[future]
            try:
                result = future.result()
                if agent_name == "researcher":
                    state["research_result"] = result.get("research_result", {})
                elif agent_name == "qa":
                    state["qa_result"] = result.get("qa_result", {})
                state["agent_trace"] += result.get("agent_trace", [])
                state["errors"] += result.get("errors", [])
            except Exception as e:
                log.error(f"[Orchestrator] Parallel agent {agent_name} raised: {e}")
                state["errors"].append(f"{agent_name}: {e}")

    # ── Step 3: Config Generator ──
    config_output = config_node(state, client, models)
    state["config_result"] = config_output.get("config_result", {})
    state["merged_memo"] = config_output.get("merged_memo", {})
    state["agent_trace"] += config_output.get("agent_trace", [])
    state["errors"] += config_output.get("errors", [])

    # ── Finalize memo ──
    final_memo = state["merged_memo"]
    final_memo["account_id"] = account_id
    final_memo["version"] = "v1"

    # Merge QA priority unknowns into memo
    qa = state.get("qa_result", {})
    existing_unknowns = final_memo.get("questions_or_unknowns", [])
    priority_unknowns = qa.get("priority_unknowns", [])
    # Deduplicate
    all_unknowns = list(dict.fromkeys(priority_unknowns + [u for u in existing_unknowns if u not in priority_unknowns]))
    final_memo["questions_or_unknowns"] = all_unknowns[:10]  # cap at 10

    pipeline_duration_ms = int((time.time() - pipeline_start) * 1000)
    log.info(f"[Orchestrator] ✅ Pipeline complete in {pipeline_duration_ms}ms | Errors: {len(state['errors'])}")

    return {
        "memo": final_memo,
        "qa_result": state["qa_result"],
        "config_enhancements": state["config_result"],
        "agent_trace": state["agent_trace"],
        "errors": state["errors"],
        "pipeline_duration_ms": pipeline_duration_ms,
        "models_used": models
    }
