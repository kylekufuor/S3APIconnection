#!/usr/bin/env python3
"""
Test script to verify that the API can handle concurrent requests without blocking.

This script simulates the scenario where a training job is started and
simultaneously a user job listing request is made.
"""

import asyncio
import base64
import time
from pathlib import Path
from typing import List

import httpx

from core.config import settings

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
API_KEY = settings.fastapi_and_wep_app_secret_key
HEADERS = {"X-API-KEY": API_KEY}


def create_base64_csv(csv_file_path: str) -> str:
    """Encodes CSV data into a base64 string with a data URI header."""
    with open(csv_file_path, "r") as f:
        csv_data = f.read()
        filename = Path(csv_file_path).name
        encoded_csv = base64.b64encode(csv_data.encode("utf-8")).decode("utf-8")
        return f"data:text/csv;name={filename};base64,{encoded_csv}"


# Test data
TRAINING_PAYLOAD = {
    "user_id": "concurrent_test_user",
    "input_file": create_base64_csv(
        "/home/work/freelancer/ai_csv_to_csv_converter_DocXPress/ai_csv_to_csv_converter_DocXPress_streamlit_POC/.cursor/rules/test_csvs/Test 2 - Raw.csv"
    ),
    "expected_output_file": create_base64_csv(
        "/home/work/freelancer/ai_csv_to_csv_converter_DocXPress/ai_csv_to_csv_converter_DocXPress_streamlit_POC/.cursor/rules/test_csvs/Test 2 - Expected.csv"
    ),
    "job_title": "Concurrent Test Job",
    "description": "Testing concurrent request handling",
    "owner": "Karim Elgazar",
    "general_instructions": "Test instructions",
    "column_instructions": {
        "total_price": "multiply `quantity` column by `price_per_unit` column",
        "order_status": "same as `order_status` input column but first letter capitalized. It has only two valid values  `Shipped` & `Pending`",
        "shipping_category": "`Standard` if order_status is `Pending`, otherwise `Express`. It has only two valid values  `Standard` & `Express`",
    },
}


async def start_training_job(client: httpx.AsyncClient, job_name: str) -> dict:
    """Start a training job and measure response time."""
    payload = TRAINING_PAYLOAD.copy()
    payload["job_title"] = f"Concurrent Test - {job_name}"
    payload["user_id"] = f"concurrent_test_user_{job_name}"

    print(f"[{job_name}] Starting training job...")
    start_time = time.time()

    try:
        response = await client.post(f"{BASE_URL}/train", json=payload, headers=HEADERS, timeout=120.0)
        elapsed = time.time() - start_time

        result = {
            "job_name": job_name,
            "operation": "training",
            "status_code": response.status_code,
            "elapsed_time": elapsed,
            "success": response.status_code == 202,
        }

        if result["success"]:
            result["job_id"] = response.json().get("job_id")
            print(f"[{job_name}] ✅ Training job started in {elapsed:.2f}s - Job ID: {result['job_id']}")
        else:
            result["error"] = response.text
            print(f"[{job_name}] ❌ Training job failed in {elapsed:.2f}s - Status: {response.status_code}")

        return result

    except Exception as e:
        elapsed = time.time() - start_time
        error_str = str(e) if str(e) else type(e).__name__
        print(f"[{job_name}] ❌ Training job exception in {elapsed:.2f}s: {error_str}")
        return {
            "job_name": job_name,
            "operation": "training",
            "success": False,
            "elapsed_time": elapsed,
            "error": error_str
        }


async def list_user_jobs(client: httpx.AsyncClient, user_id: str, request_name: str) -> dict:
    """List user jobs and measure response time."""
    print(f"[{request_name}] Listing jobs for user {user_id}...")
    start_time = time.time()

    try:
        response = await client.get(f"{BASE_URL}/users/{user_id}/jobs", headers=HEADERS, timeout=60.0)
        elapsed = time.time() - start_time

        result = {
            "job_name": request_name,
            "operation": "list_jobs",
            "status_code": response.status_code,
            "elapsed_time": elapsed,
            "success": response.status_code == 200,
        }

        if result["success"]:
            jobs = response.json()
            result["job_count"] = len(jobs)
            print(f"[{request_name}] ✅ Listed {len(jobs)} jobs in {elapsed:.2f}s")
        else:
            result["error"] = response.text
            print(f"[{request_name}] ❌ List jobs failed in {elapsed:.2f}s - Status: {response.status_code}")

        return result

    except Exception as e:
        elapsed = time.time() - start_time
        error_str = str(e) if str(e) else type(e).__name__
        print(f"[{request_name}] ❌ List jobs exception in {elapsed:.2f}s: {error_str}")
        return {
            "job_name": request_name,
            "operation": "list_jobs",
            "success": False,
            "elapsed_time": elapsed,
            "error": error_str
        }


async def health_check(client: httpx.AsyncClient, request_name: str) -> dict:
    """Health check request - should be very fast."""
    print(f"[{request_name}] Health check...")
    start_time = time.time()

    try:
        response = await client.get("http://localhost:8000/health", timeout=10.0)
        elapsed = time.time() - start_time

        result = {
            "job_name": request_name,
            "operation": "health_check",
            "status_code": response.status_code,
            "elapsed_time": elapsed,
            "success": response.status_code == 200,
        }

        if result["success"]:
            print(f"[{request_name}] ✅ Health check completed in {elapsed:.2f}s")
        else:
            print(f"[{request_name}] ❌ Health check failed in {elapsed:.2f}s - Status: {response.status_code}")

        return result

    except Exception as e:
        elapsed = time.time() - start_time
        error_str = str(e) if str(e) else type(e).__name__
        print(f"[{request_name}] ❌ Health check exception in {elapsed:.2f}s: {error_str}")
        return {
            "job_name": request_name,
            "operation": "health_check",
            "success": False,
            "elapsed_time": elapsed,
            "error": error_str
        }


async def run_concurrent_test() -> List[dict]:
    """Run concurrent requests test."""
    print("🚀 Starting concurrent requests test...")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Test 1: Training job + health checks (health checks should be fast)
        print("\n📋 Test 1: Training job + concurrent health checks")
        print("-" * 40)

        test1_start = time.time()
        tasks = [
            start_training_job(client, "Train-1"),
            health_check(client, "Health-1"),
            health_check(client, "Health-2"),
            health_check(client, "Health-3"),
        ]

        test1_results = await asyncio.gather(*tasks)
        test1_elapsed = time.time() - test1_start

        print(f"\n📊 Test 1 completed in {test1_elapsed:.2f}s total")

        # Small delay before next test
        await asyncio.sleep(1)

        # Test 2: Training job + list jobs (both might involve S3 operations)
        print("\n📋 Test 2: Training job + concurrent job listing")
        print("-" * 40)

        test2_start = time.time()
        tasks = [
            start_training_job(client, "Train-2"),
            list_user_jobs(client, "concurrent_test_user", "List-1"),
            list_user_jobs(client, "concurrent_test_user_Train-1", "List-2"),  # From previous test
        ]

        test2_results = await asyncio.gather(*tasks)
        test2_elapsed = time.time() - test2_start

        print(f"\n📊 Test 2 completed in {test2_elapsed:.2f}s total")

        # Test 3: Multiple list operations (should all be fast and concurrent)
        print("\n📋 Test 3: Multiple concurrent job listings")
        print("-" * 40)

        test3_start = time.time()
        tasks = [
            list_user_jobs(client, "concurrent_test_user", "List-A"),
            list_user_jobs(client, "concurrent_test_user_Train-1", "List-B"),
            list_user_jobs(client, "concurrent_test_user_Train-2", "List-C"),
            health_check(client, "Health-Final"),
        ]

        test3_results = await asyncio.gather(*tasks)
        test3_elapsed = time.time() - test3_start

        print(f"\n📊 Test 3 completed in {test3_elapsed:.2f}s total")

        return test1_results + test2_results + test3_results


def analyze_results(results: List[dict]) -> None:
    """Analyze and report test results."""
    print("\n" + "=" * 60)
    print("📈 CONCURRENT REQUEST TEST ANALYSIS")
    print("=" * 60)

    # Group by operation type
    operations = {}
    for result in results:
        op_type = result["operation"]
        if op_type not in operations:
            operations[op_type] = []
        operations[op_type].append(result)

    # Analyze each operation type
    for op_type, op_results in operations.items():
        print(f"\n🔍 {op_type.upper()} Operations:")
        print("-" * 30)

        successful = [r for r in op_results if r["success"]]
        failed = [r for r in op_results if not r["success"]]

        if successful:
            times = [r["elapsed_time"] for r in successful]
            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)

            print(f"  ✅ Successful: {len(successful)}/{len(op_results)}")
            print(f"  ⏱️  Average time: {avg_time:.2f}s")
            print(f"  ⚡ Fastest: {min_time:.2f}s")
            print(f"  🐌 Slowest: {max_time:.2f}s")

        if failed:
            print(f"  ❌ Failed: {len(failed)}/{len(op_results)}")
            for failure in failed:
                print(f"     - {failure['job_name']}: {failure.get('error', 'Unknown error')}")

    # Overall assessment
    print("\n🎯 OVERALL ASSESSMENT:")
    print("-" * 30)

    total_requests = len(results)
    successful_requests = len([r for r in results if r["success"]])
    success_rate = (successful_requests / total_requests) * 100 if total_requests > 0 else 0

    print(f"  📊 Total requests: {total_requests}")
    print(f"  ✅ Successful: {successful_requests}")
    print(f"  📈 Success rate: {success_rate:.1f}%")

    # Check for concurrency issues
    health_checks = operations.get("health_check", [])
    successful_health = [r for r in health_checks if r["success"]]

    if successful_health:
        health_times = [r["elapsed_time"] for r in successful_health]
        avg_health_time = sum(health_times) / len(health_times)

        # Health checks should be very fast (< 1s) if concurrency is working
        if avg_health_time < 1.0:
            print(f"  🚀 Concurrency: GOOD (health checks avg {avg_health_time:.2f}s)")
        elif avg_health_time < 5.0:
            print(f"  ⚠️  Concurrency: MODERATE (health checks avg {avg_health_time:.2f}s)")
        else:
            print(f"  🚨 Concurrency: POOR (health checks avg {avg_health_time:.2f}s)")

    print(
        "\n💡 If health checks are slow (>2s), it indicates that requests are being blocked by long-running operations."
    )


async def main():
    """Main test function."""
    try:
        results = await run_concurrent_test()
        analyze_results(results)

    except KeyboardInterrupt:
        print("\n⛔ Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
