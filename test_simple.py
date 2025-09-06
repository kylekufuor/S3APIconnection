#!/usr/bin/env python3
"""
Simple test to verify API responsiveness without complex dependencies.
"""

import asyncio
import time
import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, Any

# Configuration (you may need to adjust these)
API_BASE = "http://localhost:8000"
API_KEY = "your_secret_api_key"  # Replace with your actual API key from .env
HEADERS = {"X-API-KEY": API_KEY, "Content-Type": "application/json"}

def make_request(url: str, method: str = "GET", data: Dict[Any, Any] = None) -> Dict[str, Any]:
    """Make HTTP request using urllib (no external dependencies)."""
    try:
        if data:
            data_bytes = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=data_bytes, headers=HEADERS, method=method)
        else:
            req = urllib.request.Request(url, headers=HEADERS, method=method)
        
        start_time = time.time()
        
        with urllib.request.urlopen(req, timeout=60) as response:
            elapsed = time.time() - start_time
            response_data = json.loads(response.read().decode('utf-8'))
            
            return {
                "success": True,
                "status_code": response.getcode(),
                "data": response_data,
                "elapsed": elapsed
            }
            
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start_time
        try:
            error_data = json.loads(e.read().decode('utf-8'))
        except:
            error_data = {"error": str(e)}
            
        return {
            "success": False,
            "status_code": e.code,
            "data": error_data,
            "elapsed": elapsed
        }
        
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "success": False,
            "status_code": 0,
            "data": {"error": str(e)},
            "elapsed": elapsed
        }

async def test_concurrency():
    """Test concurrent requests using asyncio."""
    print("🚀 Testing API Concurrency (Simple Version)")
    print("=" * 50)
    
    # Test 1: Health check during job listing
    print("\n📋 Test: Concurrent health check + job listing")
    
    async def health_check():
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, make_request, f"{API_BASE}/health", "GET")
    
    async def list_jobs():
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, make_request, f"{API_BASE}/api/v1/users/test_user/jobs", "GET")
    
    # Run both requests concurrently
    start_time = time.time()
    health_result, jobs_result = await asyncio.gather(
        health_check(),
        list_jobs()
    )
    total_time = time.time() - start_time
    
    print(f"\n⏱️  Total time: {total_time:.2f}s")
    print(f"🏥 Health check: {health_result['elapsed']:.2f}s - {'✅' if health_result['success'] else '❌'}")
    print(f"📋 Job listing: {jobs_result['elapsed']:.2f}s - {'✅' if jobs_result['success'] else '❌'}")
    
    # Analysis
    if health_result['success'] and health_result['elapsed'] < 2.0:
        print("✅ Concurrency: EXCELLENT - Health check was not blocked!")
    elif health_result['success'] and health_result['elapsed'] < 5.0:
        print("⚠️  Concurrency: MODERATE - Some blocking detected")
    else:
        print("❌ Concurrency: POOR - Health check was blocked")
    
    # Test 2: Multiple quick requests
    print(f"\n📋 Test: Multiple concurrent health checks")
    
    async def multi_health():
        tasks = [health_check() for _ in range(5)]
        results = await asyncio.gather(*tasks)
        return results
    
    multi_start = time.time()
    multi_results = await multi_health()
    multi_total = time.time() - multi_start
    
    successful = sum(1 for r in multi_results if r['success'])
    avg_time = sum(r['elapsed'] for r in multi_results) / len(multi_results)
    
    print(f"⏱️  Total time: {multi_total:.2f}s")
    print(f"✅ Successful: {successful}/{len(multi_results)}")
    print(f"📊 Average time: {avg_time:.2f}s")
    
    if avg_time < 1.0 and multi_total < 2.0:
        print("🚀 Multiple requests: EXCELLENT - True concurrency achieved!")
    elif avg_time < 3.0 and multi_total < 5.0:
        print("⚠️  Multiple requests: MODERATE - Some queuing detected")
    else:
        print("❌ Multiple requests: POOR - Requests are being serialized")

def main():
    """Run the simple concurrency test."""
    try:
        asyncio.run(test_concurrency())
        
        print(f"\n💡 Interpretation:")
        print(f"   - Health checks < 1s = Excellent concurrency")
        print(f"   - Health checks 1-3s = Moderate concurrency") 
        print(f"   - Health checks > 3s = Poor concurrency (blocking)")
        print(f"\n🔧 If tests fail:")
        print(f"   1. Make sure API server is running: python main.py")
        print(f"   2. Update API_KEY in this script with your actual key")
        print(f"   3. Check server logs for errors")
        
    except KeyboardInterrupt:
        print("\n⛔ Test interrupted")
    except Exception as e:
        print(f"\n💥 Test failed: {e}")

if __name__ == "__main__":
    main()
