"""
GitHub Issues Webhook Listener
Listens for GitHub issues events on port 5000
"""
import os
import json
import hmac
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# Configuration
WEBHOOK_PORT = 5000
WEBHOOK_SECRET = os.environ.get('GITHUB_WEBHOOK_SECRET', 'default_secret')
REPO_OWNER = "RwdyLu"
REPO_NAME = "kimi-shared-brain"

# Event handlers
def handle_issue_opened(data):
    """Handle new issue created."""
    issue = data.get('issue', {})
    print(f"📝 New Issue #{issue.get('number')}: {issue.get('title')}")
    print(f"   URL: {issue.get('html_url')}")
    print(f"   User: {issue.get('user', {}).get('login')}")
    
    # TODO: Create corresponding task in tasks.json
    return {"status": "processed", "action": "issue_opened"}

def handle_issue_closed(data):
    """Handle issue closed."""
    issue = data.get('issue', {})
    print(f"✅ Issue #{issue.get('number')} closed: {issue.get('title')}")
    
    # TODO: Mark corresponding task as completed
    return {"status": "processed", "action": "issue_closed"}

def handle_issue_reopened(data):
    """Handle issue reopened."""
    issue = data.get('issue', {})
    print(f"🔄 Issue #{issue.get('number')} reopened: {issue.get('title')}")
    
    return {"status": "processed", "action": "issue_reopened"}

def handle_issue_labeled(data):
    """Handle issue labeled."""
    issue = data.get('issue', {})
    label = data.get('label', {})
    print(f"🏷️ Issue #{issue.get('number')} labeled: {label.get('name')}")
    
    return {"status": "processed", "action": "issue_labeled"}

def verify_signature(payload, signature):
    """Verify GitHub webhook signature."""
    if not signature:
        return False
    
    sha_name, signature = signature.split('=')
    if sha_name != 'sha256':
        return False
    
    mac = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), signature)

@app.route('/webhook', methods=['POST'])
def webhook():
    """Main webhook endpoint."""
    # Get signature
    signature = request.headers.get('X-Hub-Signature-256', '')
    
    # Verify signature (optional for local testing)
    # if not verify_signature(request.data, signature):
    #     return jsonify({"error": "Invalid signature"}), 401
    
    # Get event type
    event_type = request.headers.get('X-GitHub-Event', '')
    
    # Parse payload
    if request.is_json:
        data = request.get_json()
    else:
        data = json.loads(request.data)
    
    print(f"\n🔔 Received GitHub event: {event_type}")
    print(f"   Repository: {data.get('repository', {}).get('full_name')}")
    print(f"   Time: {datetime.now().isoformat()}")
    
    # Handle different event types
    handlers = {
        'issues': handle_issue_event,
        'ping': handle_ping,
    }
    
    handler = handlers.get(event_type, handle_unknown)
    result = handler(data)
    
    return jsonify(result), 200

def handle_issue_event(data):
    """Handle issues events."""
    action = data.get('action', '')
    
    action_handlers = {
        'opened': handle_issue_opened,
        'closed': handle_issue_closed,
        'reopened': handle_issue_reopened,
        'labeled': handle_issue_labeled,
        'unlabeled': lambda d: {"status": "ignored", "action": "unlabeled"},
        'edited': lambda d: {"status": "ignored", "action": "edited"},
    }
    
    handler = action_handlers.get(action, lambda d: {"status": "unknown", "action": action})
    return handler(data)

def handle_ping(data):
    """Handle ping event (webhook setup test)."""
    print("🏓 Ping received - Webhook is working!")
    return {"status": "pong", "message": "Webhook active"}

def handle_unknown(data):
    """Handle unknown events."""
    print(f"⚠️ Unknown event type")
    return {"status": "ignored", "message": "Event type not handled"}

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "github-webhook",
        "port": WEBHOOK_PORT,
        "time": datetime.now().isoformat()
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Root endpoint."""
    return jsonify({
        "service": "GitHub Issues Webhook Listener",
        "version": "1.0",
        "endpoints": {
            "/webhook": "POST - Receive GitHub webhooks",
            "/health": "GET - Health check"
        },
        "supported_events": ["issues", "ping"]
    }), 200

def start_server():
    """Start the webhook server."""
    print(f"🚀 Starting GitHub Webhook Listener on port {WEBHOOK_PORT}")
    print(f"   Endpoint: http://localhost:{WEBHOOK_PORT}/webhook")
    print(f"   Health:   http://localhost:{WEBHOOK_PORT}/health")
    print(f"\n   Configure GitHub webhook with:")
    print(f"   Payload URL: http://YOUR_SERVER_IP:{WEBHOOK_PORT}/webhook")
    print(f"   Content type: application/json")
    print(f"   Events: Issues\n")
    
    app.run(host='0.0.0.0', port=WEBHOOK_PORT, debug=False)

if __name__ == '__main__':
    start_server()
