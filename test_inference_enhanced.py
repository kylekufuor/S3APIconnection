#!/usr/bin/env python3
"""
Test script for the enhanced inference endpoint that returns base64 encoded Python script and CSV output.
"""

import asyncio
import aiohttp
import json
import base64
import os
from datetime import datetime
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = "http://localhost:8000"
API_KEY = os.getenv("FASTAPI_AND_WEP_APP_SECRET_KEY")

if not API_KEY:
    print("❌ ERROR: FASTAPI_AND_WEP_APP_SECRET_KEY not found in environment variables")
    print("Please ensure .env file is present with the correct API key")
    exit(1)

# Test configuration
CLIENT_ID = "user_32HV9SERo27z8uR7jgIHWAOQQIu"
TRAINING_JOB_ID = "50ce5c2c-e119-4103-9aa8-76bef4be027c"  # Use a completed training job

# Sample test CSV data (simple transformation test)
TEST_INPUT_CSV = """name,age,city
Alice,28,Boston
Bob,34,Seattle
Charlie,22,Denver"""

def encode_csv_to_base64(csv_content: str) -> str:
    """Encode CSV content to base64."""
    return base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')

def decode_base64_to_text(base64_content: str) -> str:
    """Decode base64 content to text."""
    return base64.b64decode(base64_content).decode('utf-8')

async def test_enhanced_inference_endpoint():
    """Test the enhanced inference endpoint."""
    print("🚀 TESTING ENHANCED INFERENCE ENDPOINT")
    print(f"📋 Client: {CLIENT_ID}")
    print(f"📋 Training Job: {TRAINING_JOB_ID}")
    print(f"🔗 API: {API_BASE_URL}")
    print("=" * 60)
    
    # Prepare request payload
    request_data = {
        "user_id": CLIENT_ID,
        "job_id": TRAINING_JOB_ID,
        "input_file": encode_csv_to_base64(TEST_INPUT_CSV),
    }
    
    async with aiohttp.ClientSession() as session:
        url = f"{API_BASE_URL}/api/v1/inference/run"
        headers = {
            "X-API-KEY": API_KEY,
            "Content-Type": "application/json"
        }
        
        print("📤 Sending inference request...")
        start_time = time.time()
        
        try:
            async with session.post(url, json=request_data, headers=headers, timeout=300) as response:  # 5 min timeout
                elapsed_time = time.time() - start_time
                status = response.status
                
                print(f"📥 Response received in {elapsed_time:.2f} seconds")
                print(f"📊 Status Code: {status}")
                
                if status == 200:
                    response_data = await response.json()
                    
                    print("\n✅ INFERENCE SUCCESSFUL!")
                    print("📋 Response Summary:")
                    print(f"  Job ID: {response_data.get('job_id')}")
                    print(f"  Status: {response_data.get('status')}")
                    print(f"  Message: {response_data.get('message')}")
                    print(f"  S3 Output Path: {response_data.get('output_s3_path')}")
                    print(f"  S3 Script Path: {response_data.get('script_s3_path')}")
                    
                    # Test base64 content
                    script_base64 = response_data.get('python_script_base64')
                    csv_base64 = response_data.get('output_csv_base64')
                    
                    if script_base64:
                        print("\n🐍 PYTHON SCRIPT CONTENT:")
                        print("=" * 40)
                        script_content = decode_base64_to_text(script_base64)
                        print(script_content[:500] + ("..." if len(script_content) > 500 else ""))
                        print("=" * 40)
                        print(f"📏 Script length: {len(script_content)} characters")
                    else:
                        print("\n❌ No Python script content received")
                    
                    if csv_base64:
                        print("\n📊 OUTPUT CSV CONTENT:")
                        print("=" * 40)
                        csv_content = decode_base64_to_text(csv_base64)
                        print(csv_content)
                        print("=" * 40)
                        print(f"📏 CSV length: {len(csv_content)} characters")
                        
                        # Validate CSV structure
                        lines = csv_content.strip().split('\n')
                        print(f"📋 CSV has {len(lines)} lines")
                        if lines:
                            print(f"📋 Header: {lines[0]}")
                    else:
                        print("\n❌ No CSV output content received")
                    
                    # Test content integrity
                    print("\n🔍 CONTENT VALIDATION:")
                    if script_base64 and csv_base64:
                        print("✅ Both script and CSV content received")
                        
                        # Basic validation
                        if "import" in script_content or "def" in script_content:
                            print("✅ Script appears to be valid Python code")
                        else:
                            print("⚠️  Script may not be valid Python code")
                            
                        if "," in csv_content and "\n" in csv_content:
                            print("✅ CSV appears to have proper structure")
                        else:
                            print("⚠️  CSV may not have proper structure")
                    else:
                        print("❌ Missing script or CSV content")
                    
                    return True
                    
                else:
                    print(f"\n❌ INFERENCE FAILED - Status: {status}")
                    try:
                        error_data = await response.json()
                        print("Error Response:")
                        print(json.dumps(error_data, indent=2))
                    except:
                        text = await response.text()
                        print(f"Raw Response: {text}")
                    return False
                    
        except asyncio.TimeoutError:
            print("❌ Request timed out after 5 minutes")
            return False
        except Exception as e:
            print(f"❌ Error during request: {e}")
            return False

async def verify_training_job_exists():
    """Verify that the training job exists before running inference."""
    print("🔍 Checking if training job exists...")
    
    async with aiohttp.ClientSession() as session:
        url = f"{API_BASE_URL}/api/v1/{CLIENT_ID}/{TRAINING_JOB_ID}"
        headers = {"X-API-KEY": API_KEY}
        
        try:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    metadata = await response.json()
                    status = metadata.get("job_status", "unknown")
                    print(f"✅ Training job found with status: {status}")
                    
                    if status == "completed":
                        return True
                    else:
                        print(f"⚠️  Training job status is '{status}', not 'completed'")
                        print("The inference may fail if the training job is not completed.")
                        return True  # Still allow the test to continue
                else:
                    print(f"❌ Training job not found - Status: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Error checking training job: {e}")
            return False

async def main():
    """Main test function."""
    print("🧪 ENHANCED INFERENCE ENDPOINT TEST")
    print("=" * 60)
    
    # Step 1: Verify training job exists
    if not await verify_training_job_exists():
        print("\n❌ Cannot proceed without a valid training job")
        return
    
    # Step 2: Test inference endpoint
    print("\n" + "=" * 60)
    success = await test_enhanced_inference_endpoint()
    
    # Final summary
    print("\n" + "=" * 60)
    print("📋 TEST SUMMARY:")
    print(f"✅ Enhanced Inference Test: {'PASSED' if success else 'FAILED'}")
    if success:
        print("🎉 The inference endpoint successfully returned base64 encoded content!")
    else:
        print("❌ The inference endpoint did not work as expected")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
