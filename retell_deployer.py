#!/usr/bin/env python3
"""
Clara AI – Retell API Deployer
================================
Direct integration with Retell AI API for deploying voice agents.
Creates LLMs with multi-state conversation flows and voice agents.
"""

import json
import os
import logging
from datetime import datetime

import requests

log = logging.getLogger("clara-retell")

RETELL_BASE = "https://api.retellai.com"


class RetellDeployer:
    """Deploy and manage Clara AI voice agents on Retell."""

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("RETELL_API_KEY", "")
        if not self.api_key:
            log.warning("No Retell API key configured.")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _request(self, method, endpoint, data=None):
        """Make an authenticated request to Retell API."""
        url = f"{RETELL_BASE}/{endpoint}"
        try:
            resp = requests.request(method, url, json=data, headers=self.headers, timeout=30)
            if resp.status_code in [200, 201]:
                return resp.json()
            else:
                log.error(f"Retell API {method} {endpoint} failed [{resp.status_code}]: {resp.text}")
                return {"error": resp.text, "status_code": resp.status_code}
        except Exception as e:
            log.error(f"Retell API request failed: {e}")
            return {"error": str(e)}

    def create_llm(self, llm_config):
        """Create a Retell LLM with conversation flow."""
        log.info("Creating Retell LLM...")
        result = self._request("POST", "create-retell-llm", llm_config)
        if "llm_id" in result:
            log.info(f"✅ LLM created: {result['llm_id']}")
        return result

    def create_agent(self, llm_id, agent_config):
        """Create a Retell voice agent attached to an LLM."""
        log.info(f"Creating Retell agent with LLM {llm_id}...")
        payload = {
            **agent_config,
            "response_engine": {
                "type": "retell-llm",
                "llm_id": llm_id
            }
        }
        result = self._request("POST", "create-agent", payload)
        if "agent_id" in result:
            log.info(f"✅ Agent created: {result['agent_id']}")
        return result

    def update_llm(self, llm_id, llm_config):
        """Update an existing Retell LLM."""
        log.info(f"Updating LLM {llm_id}...")
        return self._request("PATCH", f"update-retell-llm/{llm_id}", llm_config)

    def update_agent(self, agent_id, agent_config):
        """Update an existing Retell agent."""
        log.info(f"Updating agent {agent_id}...")
        return self._request("PATCH", f"update-agent/{agent_id}", agent_config)

    def get_agent(self, agent_id):
        """Get agent details."""
        return self._request("GET", f"get-agent/{agent_id}")

    def list_agents(self):
        """List all agents."""
        return self._request("GET", "list-agents")

    def delete_agent(self, agent_id):
        """Delete an agent."""
        log.info(f"Deleting agent {agent_id}...")
        return self._request("DELETE", f"delete-agent/{agent_id}")

    def delete_llm(self, llm_id):
        """Delete an LLM."""
        log.info(f"Deleting LLM {llm_id}...")
        return self._request("DELETE", f"delete-retell-llm/{llm_id}")

    def list_calls(self, agent_id=None, limit=50):
        """List call history, optionally filtered by agent."""
        data = {"limit": limit}
        if agent_id:
            data["filter_criteria"] = {"agent_id": [agent_id]}
        
        return self._request("POST", "v2/list-calls", data)

    def get_call(self, call_id):
        """Get details of a specific call."""
        return self._request("GET", f"v2/get-call/{call_id}")

    def deploy(self, llm_config, agent_config, account_dir=None):
        """Full deployment: Create LLM → Create Agent → Save metadata."""
        # Create LLM
        llm_result = self.create_llm(llm_config)
        if "error" in llm_result:
            return {"status": "error", "step": "create_llm", "details": llm_result}

        llm_id = llm_result["llm_id"]

        # Create Agent
        agent_result = self.create_agent(llm_id, agent_config)
        if "error" in agent_result:
            return {"status": "error", "step": "create_agent", "details": agent_result}

        agent_id = agent_result["agent_id"]

        metadata = {
            "agent_id": agent_id,
            "llm_id": llm_id,
            "agent_name": agent_config.get("agent_name", ""),
            "deployed_at": datetime.now().isoformat(),
            "version": "deployed",
            "voice_id": agent_config.get("voice_id", ""),
        }

        # Save metadata to disk
        if account_dir:
            os.makedirs(account_dir, exist_ok=True)
            meta_path = os.path.join(account_dir, "retell_deployment.json")
            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=4)
            log.info(f"Saved deployment metadata: {meta_path}")

        return {
            "status": "success",
            "agent_id": agent_id,
            "llm_id": llm_id,
            "metadata": metadata
        }

    def redeploy(self, account_dir, llm_config, agent_config):
        """Update existing deployment or create new one."""
        meta_path = os.path.join(account_dir, "retell_deployment.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                existing = json.load(f)
            
            llm_id = existing.get("llm_id")
            agent_id = existing.get("agent_id")

            if llm_id and agent_id:
                log.info(f"Updating existing deployment: agent={agent_id}, llm={llm_id}")
                llm_result = self.update_llm(llm_id, llm_config)
                agent_result = self.update_agent(agent_id, agent_config)

                metadata = {
                    **existing,
                    "updated_at": datetime.now().isoformat(),
                    "version": "updated"
                }
                with open(meta_path, "w") as f:
                    json.dump(metadata, f, indent=4)

                return {
                    "status": "updated",
                    "agent_id": agent_id,
                    "llm_id": llm_id
                }

        # No existing deployment, create new
        return self.deploy(llm_config, agent_config, account_dir)
