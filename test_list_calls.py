import json, os
from retell_deployer import RetellDeployer

account_id = "ben"
deploy_path = os.path.join("outputs/accounts", account_id, "retell_deployment.json")

if not os.path.exists(deploy_path):
    print("No deploy path")
else:
    with open(deploy_path) as f:
        deploy = json.load(f)
    print("Agent:", deploy.get("agent_id"))
    deployer = RetellDeployer()
    calls_raw = deployer.list_calls(deploy.get("agent_id"))
    print("Calls raw type:", type(calls_raw))
    if isinstance(calls_raw, list):
        print("Count:", len(calls_raw))
    else:
        print("Response:", calls_raw)
