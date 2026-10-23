#!/usr/bin/env python3
"""
Quick test script for the careloop server.
Tests MCP tools via local client and HTTP endpoints.
"""

import os
from datetime import datetime, timedelta
from mcp.client import ClientSession
import asyncio
import httpx
import json
import requests

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "careloop-demo-change-me")
r = requests.post(f"https://ntfy.sh/{NTFY_TOPIC}",
                  data="test from python".encode("utf-8"),
                  headers={"Title": "URGENT: Heart Pill", "Priority": "high"},
                  timeout=5)
print(r.status_code, r.text)

async def test_mcp_tools():
    """Test MCP tools directly."""
    print("🧪 Testing MCP Tools...\n")
    
    # Note: These would be tested via MCP client connection
    # For now, we'll just test the HTTP API
    pass

async def test_http_api():
    """Test HTTP endpoints."""
    async with httpx.AsyncClient() as client:
        # Test adding a dose
        future_time = (datetime.now() + timedelta(minutes=5)).isoformat()
        
        print("📋 Testing /api/state endpoint...")
        response = await client.get("http://localhost:8000/api/state")
        state = response.json()
        print(f"✓ Got state with {len(state['doses'])} doses")
        print(f"  Alerts: {state['alerts']['urgent_count']} urgent, {state['alerts']['warning_count']} warnings\n")
        
        # Test dashboard
        print("🎨 Testing dashboard endpoint...")
        response = await client.get("http://localhost:8000/")
        if response.status_code == 200:
            print("✓ Dashboard HTML loaded successfully\n")
        else:
            print(f"✗ Dashboard failed: {response.status_code}\n")

if __name__ == "__main__":
    print("🚀 Testing CareLoop Server\n")
    asyncio.run(test_http_api())
    print("✅ HTTP API tests completed!")
