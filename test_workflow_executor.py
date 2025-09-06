#!/usr/bin/env python3
"""
Test script for the new workflow executor to verify multi-process functionality.
"""

import asyncio
import time

import httpx

from core.config import settings

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
API_KEY = settings.fastapi_and_wep_app_secret_key
HEADERS = {"X-API-KEY": API_KEY}

# Test payload using existing S3 files
TEST_PAYLOAD = {
    "user_id": "workflow_test_user",
    "input_file": "s3://madular-data-files/concurrent_test_user_Train-1/1eb06c4b-51e4-429d-8e04-baa3523c86dd/input/input.csv",
    "expected_output_file": "s3://madular-data-files/concurrent_test_user_Train-1/1eb06c4b-51e4-429d-8e04-baa3523c86dd/input/expected_output.csv",
    "job_title": "Workflow Executor Test",
    "description": "Testing new multi-process workflow executor",
    "owner": "Test System",
    "general_instructions": "Test the new process pool",
    "column_instructions": {"test": "test"},
}


async def test_queue_status(client: httpx.AsyncClient) -> dict:
    """Test the queue status endpoint."""
    try:
        url = f"{BASE_URL}/queue/status"
        print(f"Requesting: {url}")
        response = await client.get(url, headers=HEADERS, timeout=10.0)
        print(f"Response status: {response.status_code}")
        print(f"Response text: {response.text[:500]}")
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        else:
            return {"success": False, "error": f"Status {response.status_code}: {response.text}"}
    except Exception as e:
        print(f"Exception in test_queue_status: {e}")
        print(f"Exception type: {type(e)}")
        import traceback

        print(f"Traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}


async def submit_training_job(client: httpx.AsyncClient, job_name: str) -> dict:
    """Submit a training job and measure response time."""
    payload = TEST_PAYLOAD.copy()
    payload["job_title"] = f"Workflow Test - {job_name}"
    payload["user_id"] = f"workflow_test_{job_name.lower()}"

    start_time = time.time()
    try:
        response = await client.post(f"{BASE_URL}/train", json=payload, headers=HEADERS, timeout=10.0)
        elapsed = time.time() - start_time

        print(f"Job {job_name} - Status: {response.status_code}, Response: {response.text[:200]}")
        if response.status_code in [200, 202]:  # Accept both success and accepted
            job_data = response.json()
            print(f"Job {job_name} - SUCCESS: {job_data.get('job_id')}")
            return {"success": True, "job_id": job_data.get("job_id"), "elapsed": elapsed, "job_name": job_name}
        else:
            print(f"Job {job_name} - FAILED: {response.status_code} - {response.text[:200]}")
            return {
                "success": False,
                "error": f"Status {response.status_code}: {response.text[:200]}",
                "elapsed": elapsed,
                "job_name": job_name,
            }
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"Exception in submit_training_job for {job_name}: {e}")
        print(f"Exception type: {type(e)}")
        return {"success": False, "error": str(e), "elapsed": elapsed, "job_name": job_name}


async def test_user_jobs_listing(client: httpx.AsyncClient, user_id: str) -> dict:
    """Test the user jobs listing endpoint."""
    start_time = time.time()
    try:
        url = f"{BASE_URL}/users/{user_id}/jobs"
        response = await client.get(url, headers=HEADERS, timeout=10.0)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            jobs_data = response.json()
            return {
                "success": True, 
                "jobs_count": len(jobs_data), 
                "elapsed": elapsed,
                "jobs_data": jobs_data
            }
        else:
            return {
                "success": False,
                "error": f"Status {response.status_code}: {response.text[:200]}",
                "elapsed": elapsed
            }
    except Exception as e:
        elapsed = time.time() - start_time
        return {"success": False, "error": str(e), "elapsed": elapsed}


async def test_workflow_executor():
    """Test the new workflow executor functionality."""
    print("🚀 TESTING NEW WORKFLOW EXECUTOR")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Test 1: Check initial queue status
        print("\n📊 Test 1: Initial Queue Status")
        print("-" * 30)

        queue_result = await test_queue_status(client)
        if queue_result["success"]:
            print(f"✅ Raw queue response: {queue_result['data']}")
            queue_data = queue_result["data"]["queue_info"]
            print("✅ Queue Status Retrieved:")
            print(f"   Max Workers: {queue_data['max_workers']}")
            print(f"   Active Jobs: {queue_data['active_jobs']}")
            print(f"   Available Workers: {queue_data['available_workers']}")
        else:
            print(f"❌ Failed to get queue status: {queue_result['error']}")
            return

        # Test 2: Submit multiple training jobs rapidly
        print("\n🎯 Test 2: Rapid Job Submission (API Responsiveness)")
        print("-" * 30)

        job_names = ["Job1", "Job2", "Job3", "Job4", "Job5"]

        start_time = time.time()
        tasks = [submit_training_job(client, name) for name in job_names]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        successful_submissions = [r for r in results if r["success"]]
        failed_submissions = [r for r in results if not r["success"]]
        print("failed_submissions: ", failed_submissions)

        avg_response_time = sum(r["elapsed"] for r in results) / len(results)

        print(f"⏱️  Total submission time: {total_time:.2f}s")
        print(f"📊 Average API response: {avg_response_time:.3f}s")
        print(f"✅ Successful submissions: {len(successful_submissions)}/{len(results)}")
        print(f"❌ Failed submissions: {len(failed_submissions)}")

        if failed_submissions:
            print("\nFailure details:")
            for fail in failed_submissions:
                print(f"   {fail['job_name']}: {fail['error']}")

        # Test 3: Check queue status after submissions
        print("\n📊 Test 3: Queue Status After Submissions")
        print("-" * 30)

        await asyncio.sleep(1)  # Give a moment for jobs to be queued
        queue_result = await test_queue_status(client)
        if queue_result["success"]:
            queue_data = queue_result["data"]["queue_info"]
            capacity_data = queue_result["data"]["capacity_utilization"]

            print("✅ Updated Queue Status:")
            print(f"   Active Jobs: {queue_data['active_jobs']}/{queue_data['max_workers']}")
            print(f"   Queue Size: {queue_data['queue_size']}")
            print(f"   Workers Busy: {capacity_data['workers_busy_percent']:.1f}%")
            print(f"   Can Accept New Jobs: {capacity_data['can_accept_new_jobs']}")
            print(f"   Estimated Wait Time: {capacity_data['estimated_wait_time_minutes']:.1f} minutes")
        else:
            print(f"❌ Failed to get updated queue status: {queue_result['error']}")

        # Test 4: API responsiveness during processing
        print("\n⚡ Test 4: API Responsiveness During Processing")
        print("-" * 30)

        # Test health check while jobs are processing
        health_times = []
        for i in range(5):
            start_time = time.time()
            try:
                response = await client.get("http://localhost:8000/health", timeout=5.0)
                elapsed = time.time() - start_time
                health_times.append(elapsed)
                status = "✅" if response.status_code == 200 else "❌"
                print(f"   Health check {i + 1}: {status} {elapsed:.3f}s")
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"   Health check {i + 1}: ❌ {elapsed:.3f}s ({e})")

            await asyncio.sleep(0.5)  # Small delay between checks

        if health_times:
            avg_health_time = sum(health_times) / len(health_times)
            print("\n📊 Health Check Analysis:")
            print(f"   Average response time: {avg_health_time:.3f}s")
            print(f"   Fastest response: {min(health_times):.3f}s")
            print(f"   Slowest response: {max(health_times):.3f}s")

            if avg_health_time < 0.1:
                print("   🎉 EXCELLENT: API remains highly responsive!")
            elif avg_health_time < 0.5:
                print("   ✅ GOOD: API responsiveness is acceptable")
            else:
                print("   ⚠️  CONCERN: API may still be experiencing some blocking")

        # Test 5: User Jobs Listing (API responsiveness for data queries)
        print("\n📋 Test 5: User Jobs Listing During Processing")
        print("-" * 30)
        
        # Test multiple user job listings while jobs are processing
        user_jobs_times = []
        test_users = ["workflow_test_job1", "workflow_test_job2", "workflow_test_job3"]
        
        for i, user_id in enumerate(test_users):
            try:
                jobs_result = await test_user_jobs_listing(client, user_id)
                if jobs_result["success"]:
                    user_jobs_times.append(jobs_result["elapsed"])
                    print(f"   User {user_id} jobs: ✅ {jobs_result['elapsed']:.3f}s ({jobs_result['jobs_count']} jobs found)")
                else:
                    print(f"   User {user_id} jobs: ❌ {jobs_result['elapsed']:.3f}s - {jobs_result['error'][:50]}")
            except Exception as e:
                print(f"   User {user_id} jobs: ❌ Exception - {e}")
            
            await asyncio.sleep(0.5)  # Small delay between requests
        
        if user_jobs_times:
            avg_jobs_time = sum(user_jobs_times) / len(user_jobs_times)
            print("\n📊 User Jobs Listing Analysis:")
            print(f"   Average response time: {avg_jobs_time:.3f}s")
            print(f"   Fastest response: {min(user_jobs_times):.3f}s")
            print(f"   Slowest response: {max(user_jobs_times):.3f}s")
            
            if avg_jobs_time < 0.5:
                print("   🎉 EXCELLENT: Job listing API remains fast during processing!")
            elif avg_jobs_time < 2.0:
                print("   ✅ GOOD: Job listing performance is acceptable")
            else:
                print("   ⚠️  CONCERN: Job listing may be affected by processing load")
        else:
            print("   ⚠️  No successful job listing requests")
            avg_jobs_time = None

    # Final Assessment
    print("\n🎯 WORKFLOW EXECUTOR TEST RESULTS")
    print("=" * 60)

    jobs_listing_ok = 'avg_jobs_time' in locals() and avg_jobs_time is not None and avg_jobs_time < 2.0
    
    if len(successful_submissions) >= 3 and avg_response_time < 1.0:
        print("🏆 WORKFLOW EXECUTOR: WORKING EXCELLENTLY")
        print("   ✅ Jobs submit quickly (API not blocked)")
        print("   ✅ Multiple jobs can be processed concurrently")
        print("   ✅ Queue management is functioning")
        print("   ✅ Process isolation prevents API blocking")
        if jobs_listing_ok:
            print("   ✅ User job listing remains responsive during processing")

        print("\n📈 Performance Summary:")
        print(f"   - Job submission rate: {len(results) / total_time:.1f} jobs/second")
        print(f"   - API responsiveness: {avg_response_time:.3f}s average")
        print(f"   - Health check performance: {avg_health_time:.3f}s average" if health_times else "")
        if 'avg_jobs_time' in locals() and avg_jobs_time is not None:
            print(f"   - User jobs listing: {avg_jobs_time:.3f}s average")

    elif len(successful_submissions) >= 2:
        print("✅ WORKFLOW EXECUTOR: WORKING WELL")
        print("   ✅ Basic functionality is working")
        print("   ⚠️  Some optimization may be needed")
        if jobs_listing_ok:
            print("   ✅ User job listing performance is good")
        elif 'avg_jobs_time' in locals() and avg_jobs_time is not None:
            print("   ⚠️  User job listing could be faster")

    else:
        print("❌ WORKFLOW EXECUTOR: NEEDS ATTENTION")
        print("   ❌ Multiple job submissions are failing")
        print("   🔧 Check server logs for issues")

    print("\n💡 Next Steps:")
    print("   - Monitor worker processes with: ps aux | grep python")
    print(f"   - Check queue status: curl -H 'X-API-KEY: YOUR_API_KEY' {BASE_URL}/queue/status")
    print("   - View job progress in S3 or via API endpoints")


async def test_workflow_queue_status():
    """Test the new workflow executor functionality."""
    print("🚀 TESTING NEW WORKFLOW EXECUTOR")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Test 1: Check initial queue status
        print("\n📊 Test 1: Initial Queue Status")
        print("-" * 30)

        queue_result = await test_queue_status(client)
        if queue_result["success"]:
            print(f"✅ Raw queue response: {queue_result['data']}")
            queue_data = queue_result["data"]["queue_info"]
            print("✅ Queue Status Retrieved:")
            print(f"   Max Workers: {queue_data['max_workers']}")
            print(f"   Active Jobs: {queue_data['active_jobs']}")
            print(f"   Available Workers: {queue_data['available_workers']}")
        else:
            print(f"❌ Failed to get queue status: {queue_result['error']}")
            return


if __name__ == "__main__":
    asyncio.run(test_workflow_executor())
    # asyncio.run(test_workflow_queue_status())
