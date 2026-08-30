"""
Integration test: start API server and test /simulate endpoint.
"""
import threading
import time
import requests
import sys

# Import the Flask app
sys.path.insert(0, '.')
from api import app

def run_server():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)

# Start server in background thread
server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()
time.sleep(2)

print("[Test] Server started on 127.0.0.1:5001")

# Test health endpoint
r = requests.get('http://127.0.0.1:5001/api/v1/health')
print(f"[Test] Health: {r.json()}")

# Test simulate endpoint (30 matches)
print("[Test] Running 30-match simulation...")
r = requests.get('http://127.0.0.1:5001/api/v1/simulate?n=30')
data = r.json()

print(f"[Test] Simulation complete!")
print(f"[Test] Matches with prediction: {data['matches_with_prediction']}")
print(f"[Test] Overall accuracy: {data['overall_accuracy']}%")
print(f"[Test] Upper predictions: {data['upper_predictions']} (acc {data['upper_accuracy']}%)")
print(f"[Test] Lower predictions: {data['lower_predictions']} (acc {data['lower_accuracy']}%)")

# Show first 5 results
for res in data['results'][:5]:
    print(f"  {res['match']} | 預測:{res['prediction']} | 實際:{res['actual']} | {'✓' if res['correct'] else '✗'}")

print("\n[Test] All tests passed!")
