#!/usr/bin/env python3
"""
WTP IAQ/AQ Live Payload Probe

Validates live WTP sensor payloads for iaq_sensor, aq_sensor, air_quality_sensor
to confirm field names and structure match integration descriptors.

Usage:
  python3 scripts/probe_wtp_iaq_payloads.py \
    --hub-url http://10.0.61.132 \
    --api-token <token>

Environment variables:
  SINUM_WTP_TOKEN: API token (alternative to --api-token)
"""

import argparse
import json
import os
import sys
from datetime import datetime

try:
    import aiohttp
    import asyncio
except ImportError:
    print("ERROR: aiohttp required. Install: pip install aiohttp")
    sys.exit(1)


async def probe_iaq_sensors(hub_url: str, api_token: str) -> dict:
    """Query WTP hub for IAQ/AQ sensor devices and validate payloads."""
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "hub_url": hub_url,
        "devices": [],
        "validation": {
            "all_pass": True,
            "issues": [],
        }
    }
    
    headers = {"Authorization": f"Bearer {api_token}"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{hub_url}/api/v1/devices", headers=headers) as resp:
                if resp.status != 200:
                    results["validation"]["all_pass"] = False
                    results["validation"]["issues"].append(f"API error: {resp.status}")
                    return results
                
                devices = await resp.json()
                
                # Expected IAQ/AQ device types
                iaq_types = ["iaq_sensor", "aq_sensor", "air_quality_sensor"]
                
                for device in devices:
                    if device.get("type") in iaq_types:
                        device_info = {
                            "id": device.get("id"),
                            "name": device.get("name"),
                            "type": device.get("type"),
                            "state": device.get("state", {}),
                            "validation": {
                                "pass": True,
                                "issues": [],
                            }
                        }
                        
                        # Expected field keys from descriptors/sensor.py
                        expected_fields = {
                            "iaq": ("Index", None),
                            "air_quality": ("Percentage", "%"),
                            "pm25": ("µg/m³", "mdi:lung"),
                            "pm10": ("µg/m³", "mdi:lung"),
                        }
                        
                        state = device_info["state"]
                        
                        # Check for expected fields
                        for field in expected_fields:
                            if field not in state:
                                device_info["validation"]["pass"] = False
                                device_info["validation"]["issues"].append(
                                    f"Missing expected field: {field}"
                                )
                        
                        # Check for unexpected fields (future-proofing)
                        unexpected = set(state.keys()) - set(expected_fields.keys())
                        for field in unexpected:
                            if not field in ["temperature", "humidity", "updated_at"]:  # OK extras
                                device_info["validation"]["issues"].append(
                                    f"Unexpected field (may be new): {field} = {state[field]}"
                                )
                        
                        if not device_info["validation"]["pass"]:
                            results["validation"]["all_pass"] = False
                        
                        results["devices"].append(device_info)
    
    except Exception as e:
        results["validation"]["all_pass"] = False
        results["validation"]["issues"].append(f"Exception: {str(e)}")
    
    return results


async def main():
    parser = argparse.ArgumentParser(description="WTP IAQ/AQ Payload Probe")
    parser.add_argument("--hub-url", required=True, help="Hub URL (http://10.0.x.x)")
    parser.add_argument("--api-token", help="API token (or set SINUM_WTP_TOKEN)")
    args = parser.parse_args()
    
    api_token = args.api_token or os.getenv("SINUM_WTP_TOKEN")
    if not api_token:
        print("ERROR: API token required (--api-token or SINUM_WTP_TOKEN env var)")
        sys.exit(1)
    
    print(f"Probing: {args.hub_url}")
    print("Querying IAQ/AQ sensors...\n")
    
    results = await probe_iaq_sensors(args.hub_url, api_token)
    
    # Print results
    print(f"{'='*60}")
    print(f"Probe Results: {results['timestamp']}")
    print(f"Hub: {results['hub_url']}")
    print(f"{'='*60}\n")
    
    if results["devices"]:
        print(f"Found {len(results['devices'])} IAQ/AQ sensors:\n")
        for i, device in enumerate(results["devices"], 1):
            print(f"Device {i}: {device['name']} (type: {device['type']})")
            print(f"  State: {json.dumps(device['state'], indent=4)}")
            if device["validation"]["pass"]:
                print(f"  ✅ Validation: PASS")
            else:
                print(f"  ❌ Validation: FAIL")
                for issue in device["validation"]["issues"]:
                    print(f"     - {issue}")
            print()
    else:
        print("❌ No IAQ/AQ sensors found on hub")
    
    if results["validation"]["all_pass"]:
        print(f"{'='*60}")
        print("✅ All devices PASS validation")
        print("Descriptors match live payloads. No changes needed.")
        print(f"{'='*60}\n")
        return 0
    else:
        print(f"{'='*60}")
        print("❌ Validation FAILED")
        for issue in results["validation"]["issues"]:
            print(f"  - {issue}")
        print(f"{'='*60}\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
