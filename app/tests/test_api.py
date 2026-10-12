import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import app

def test_health():
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200