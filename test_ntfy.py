import os
import requests

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "careloop-demo-change-me")
r = requests.post(f"https://ntfy.sh/{NTFY_TOPIC}",
                  data="test from python".encode("utf-8"),
                  headers={"Title": "URGENT: Heart Pill", "Priority": "high"},
                  timeout=5)
print(r.status_code, r.text)
