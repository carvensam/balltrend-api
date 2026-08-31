from api import app
import json

client = app.test_client()
resp = client.get('/api/v1/simulate20')
data = resp.get_json()
print(json.dumps(data, indent=2, ensure_ascii=False))
