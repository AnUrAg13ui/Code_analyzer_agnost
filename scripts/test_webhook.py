import hmac
import hashlib
import json
import requests

# Configuration
URL = "http://localhost:8000/webhook/github"
SECRET = "code_analyzer_secret"

# Payload to simulate a PR opened event
payload = {
    "action": "opened",
    "pull_request": {
        "number": 58,
        "title": "Deep Analysis Test",
        "user": {"login": "soumyajit4419"},
        "head": {"sha": "latest"}
    },
    "repository": {
        "full_name": "soumyajit4419/Portfolio",
        "name": "Portfolio",
        "owner": {"login": "soumyajit4419"}
    }
}

body = json.dumps(payload)

# Calculate HMAC signature
signature = hmac.new(
    SECRET.encode(),
    body.encode(),
    hashlib.sha256
).hexdigest()

headers = {
    "Content-Type": "application/json",
    "X-GitHub-Event": "pull_request",
    "X-Hub-Signature-256": f"sha256={signature}"
}

print(f"Sending webhook to {URL}...")
resp = requests.post(URL, data=body, headers=headers)

if resp.status_code == 202:
    print("✅ Webhook accepted!")
    print(resp.json())
else:
    print(f"❌ Webhook failed with status {resp.status_code}")
    print(resp.text)
