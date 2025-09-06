#!/usr/bin/env python3
"""
Simple diagnostic test to debug API and S3 connectivity issues.
"""

import asyncio
import time
import httpx
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from pathlib import Path

# Add the current directory to Python path to import local modules
import sys
sys.path.insert(0, str(Path(__file__).parent))

try:
    from core.config import settings
    CONFIG_LOADED = True
    print("✅ Configuration loaded successfully")
    print(f"   - AWS Bucket: {settings.aws_bucket_name}")
    print(f"   - Debug mode: {settings.debug}")
except Exception as e:
    CONFIG_LOADED = False
    print(f"❌ Failed to load configuration: {e}")

def test_s3_connectivity():
    """Test S3 connectivity and permissions."""
    print("\n🔍 Testing S3 Connectivity...")
    
    if not CONFIG_LOADED:
        print("❌ Cannot test S3 - configuration not loaded")
        return False
    
    try:
        # Create S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key
        )
        
        # Test basic connectivity
        print(f"   Testing access to bucket: {settings.aws_bucket_name}")
        
        # List first few objects to test permissions
        response = s3_client.list_objects_v2(
            Bucket=settings.aws_bucket_name, 
            MaxKeys=5
        )
        
        if 'Contents' in response:
            print(f"✅ S3 connectivity OK - Found {len(response['Contents'])} objects")
        else:
            print("✅ S3 connectivity OK - Empty bucket or no objects")
        
        return True
        
    except NoCredentialsError:
        print("❌ S3 Error: AWS credentials not found")
        return False
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchBucket':
            print(f"❌ S3 Error: Bucket '{settings.aws_bucket_name}' does not exist")
        elif error_code == 'AccessDenied':
            print("❌ S3 Error: Access denied - check your AWS permissions")
        else:
            print(f"❌ S3 Error: {error_code} - {e}")
        return False
    except Exception as e:
        print(f"❌ S3 Error: Unexpected error - {e}")
        return False

async def test_api_connectivity():
    """Test API connectivity."""
    print("\n🔍 Testing API Connectivity...")
    
    if not CONFIG_LOADED:
        print("❌ Cannot test API - configuration not loaded")
        return False
    
    base_url = "http://localhost:8000"
    headers = {"X-API-KEY": settings.fastapi_and_wep_app_secret_key}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Test health endpoint
            print("   Testing health endpoint...")
            start_time = time.time()
            response = await client.get(f"{base_url}/health")
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                print(f"✅ Health check OK ({elapsed:.2f}s)")
                print(f"   Response: {response.json()}")
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False
            
            # Test protected endpoint (user jobs)
            print("   Testing protected endpoint...")
            start_time = time.time()
            response = await client.get(
                f"{base_url}/api/v1/users/test_debug_user/jobs", 
                headers=headers
            )
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                jobs = response.json()
                print(f"✅ Protected endpoint OK ({elapsed:.2f}s)")
                print(f"   Found {len(jobs)} jobs for test user")
            else:
                print(f"❌ Protected endpoint failed: {response.status_code}")
                if response.status_code == 401:
                    print("   Issue: Authentication failed - check API key")
                elif response.status_code == 500:
                    print("   Issue: Server error - check logs")
                print(f"   Response: {response.text[:200]}")
                return False
                
        return True
        
    except httpx.ConnectError:
        print("❌ API Error: Cannot connect to server - is it running?")
        return False
    except httpx.TimeoutException:
        print("❌ API Error: Request timed out")
        return False
    except Exception as e:
        print(f"❌ API Error: {e}")
        return False

async def test_simple_job_creation():
    """Test creating a simple job."""
    print("\n🔍 Testing Simple Job Creation...")
    
    if not CONFIG_LOADED:
        print("❌ Cannot test job creation - configuration not loaded")
        return False
    
    base_url = "http://localhost:8000"
    headers = {"X-API-KEY": settings.fastapi_and_wep_app_secret_key}
    
    # Simple training payload
    payload = {
        "user_id": "test_debug_user",
        "input_file": "s3://madular-data-files/Test 2 - Raw.csv",
        "expected_output_file": "s3://madular-data-files/Test 2 - Expected.csv",
        "job_title": "Debug Test Job",
        "description": "Simple debug test",
        "owner": "Debug Test",
        "general_instructions": "Test",
        "column_instructions": {"test": "test"}
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            print("   Creating training job...")
            start_time = time.time()
            
            response = await client.post(
                f"{base_url}/api/v1/train",
                json=payload,
                headers=headers
            )
            
            elapsed = time.time() - start_time
            
            if response.status_code == 202:
                result = response.json()
                print(f"✅ Job creation OK ({elapsed:.2f}s)")
                print(f"   Job ID: {result.get('job_id')}")
                print(f"   Status: {result.get('status')}")
                return True
            else:
                print(f"❌ Job creation failed: {response.status_code}")
                print(f"   Response: {response.text[:300]}")
                return False
                
    except Exception as e:
        print(f"❌ Job creation error: {e}")
        return False

async def main():
    """Run all diagnostic tests."""
    print("🔧 API DIAGNOSTIC TEST")
    print("=" * 50)
    
    # Test S3 connectivity
    s3_ok = test_s3_connectivity()
    
    # Test API connectivity  
    api_ok = await test_api_connectivity()
    
    # Test job creation if both S3 and API are working
    if s3_ok and api_ok:
        job_ok = await test_simple_job_creation()
    else:
        job_ok = False
        print("\n⚠️  Skipping job creation test due to S3/API issues")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 DIAGNOSTIC SUMMARY")
    print("=" * 50)
    print(f"S3 Connectivity:     {'✅ OK' if s3_ok else '❌ FAILED'}")
    print(f"API Connectivity:    {'✅ OK' if api_ok else '❌ FAILED'}")
    print(f"Job Creation:        {'✅ OK' if job_ok else '❌ FAILED'}")
    
    if s3_ok and api_ok and job_ok:
        print("\n🎉 All tests passed! The API should handle concurrent requests properly.")
        print("💡 If concurrent tests still fail, the issue may be:")
        print("   - Network latency to S3")
        print("   - Large file processing times")
        print("   - HTTP client timeout settings")
    else:
        print("\n🚨 Some tests failed. Fix these issues before testing concurrency:")
        if not s3_ok:
            print("   - Check AWS credentials and S3 bucket access")
        if not api_ok:
            print("   - Ensure the API server is running")
            print("   - Check API key configuration")
        if not job_ok and s3_ok and api_ok:
            print("   - Check server logs for job creation errors")

if __name__ == "__main__":
    asyncio.run(main())
