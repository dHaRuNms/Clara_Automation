import sys
import json
import os
import requests
from datetime import datetime

RETELL_API_KEY = "key_8b72c05fa199b67482f7bcc7e083"

def fetch_latest_call():
    url = "https://api.retellai.com/v2/list-calls"
    headers = {
        "Authorization": f"Bearer {RETELL_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"limit": 1, "sort_order": "descending"}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            return {"error": f"Failed: {response.text}"}
            
        calls = response.json()
        if not calls:
            return {"error": "No calls found"}
            
        latest_call = calls[0]
        
        # Format the output for n8n
        result = {
            "call_id": latest_call.get('call_id'),
            "request_received_at": datetime.fromtimestamp(latest_call.get('start_timestamp')/1000).strftime('%Y-%m-%d %H:%M:%S'),
            "customer_name": "Extracted from Summary",
            "appointment_time": "Extracted from Summary",
            "summary": latest_call.get('call_analysis', {}).get('call_summary', 'N/A'),
            "transcript": latest_call.get('transcript', 'N/A')
        }
        
        # Print only the JSON so n8n can parse it
        print(json.dumps([result]))
        return result
        
    except Exception as e:
        print(json.dumps([{"error": str(e)}]))
        return None

if __name__ == "__main__":
    fetch_latest_call()