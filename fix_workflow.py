import json

with open('workflows/clara_pipeline.json', 'r') as f:
    data = json.load(f)

# Remove the Process One-by-One node
new_nodes = [n for n in data['nodes'] if n['name'] != '📦 Process One-by-One']
data['nodes'] = new_nodes

# Update connections
conns = data['connections']

# Parse & Sort Files -> Demo or Onboarding
conns['🔀 Parse & Sort Files'] = {
    "main": [
        [{"node": "📋 Demo or Onboarding?", "type": "main", "index": 0}]
    ]
}

# Log Result -> Batch Summary Report
conns['📋 Log Result'] = {
    "main": [
        [{"node": "📊 Batch Summary Report", "type": "main", "index": 0}]
    ]
}

# Remove connections FROM Process One-by-One
if '📦 Process One-by-One' in conns:
    del conns['📦 Process One-by-One']

with open('workflows/clara_pipeline.json', 'w') as f:
    json.dump(data, f, indent=2)

print("Workflow fixed")
