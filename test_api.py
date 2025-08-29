import base64
import json

import requests

from core.config import settings

# --- Configuration ---
BASE_URL = "http://localhost:8000/api/v1"
API_KEY = settings.fastapi_and_wep_app_secret_key
HEADERS = {"X-API-KEY": API_KEY}

# --- Sample Data ---

# 1. Sample Input CSV Data
input_csv_data = "quantity,price_per_unit,order_status\n10,2.5,pending\n5,10.0,shipped\n1,100.0,pending\n"

# 2. Sample Expected Output CSV Data
expected_output_csv_data = (
    "total_price,order_status,shipping_category\n25.0,Pending,Standard\n50.0,Shipped,Express\n100.0,Pending,Standard\n"
)


def create_base64_csv(csv_data: str, filename: str) -> str:
    """Encodes CSV data into a base64 string with a data URI header."""
    encoded_csv = base64.b64encode(csv_data.encode("utf-8")).decode("utf-8")
    return f"data:text/csv;name={filename};base64,{encoded_csv}"


def test_training_endpoint():
    """Tests the /api/v1/train endpoint."""
    print("--- Starting API Test for /api/v1/train ---")

    # --- Prepare Payload ---
    # input_file_base64 = create_base64_csv(input_csv_data, "input.csv")
    # expected_output_file_base64 = create_base64_csv(expected_output_csv_data, "expected.csv")
    payload = {
        "user_id": "test_user_123",
        "input_file": "s3://madular-data-files/Test 2 - Raw.csv",
        "expected_output_file": "s3://madular-data-files/Test 2 - Expected.csv",
        "job_title": "Test 2",
        "description": "check the api with test 2",
        "owner": "Karim",
        "general_instructions": "",
        "column_instructions": {
            "total_price": "multiply `quantity`column by `price_per_unit` column",
            "order_status": "same as `order_status` input column but first letter capitalized. It has only two valid values  `Shipped` & `Pending`",
            "shipping_category": "`Standard` if order_status is `Pending`, otherwise `Express`. It has only two valid values  `Standard` & `Express`",
        },
    }

    # --- Send Request ---
    try:
        print(f"Sending POST request to {BASE_URL}/train")
        response = requests.post(f"{BASE_URL}/train", json=payload, headers=HEADERS, timeout=30)

        # --- Print Response ---
        print(f"\nResponse Status Code: {response.status_code}")

        if response.status_code == 202:
            print("\nSuccessfully started training job!")
            print("Response JSON:")
            print(json.dumps(response.json(), indent=2))
        else:
            print("\nError starting training job.")
            try:
                print("Error Response JSON:")
                print(json.dumps(response.json(), indent=2))
            except json.JSONDecodeError:
                print("Could not decode JSON response.")
                print(f"Raw Response Text: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"\nAn error occurred while sending the request: {e}")

    print("\n--- Test Finished ---")


def test_inference_endpoint():
    """Tests the /api/v1/inference/run endpoint."""
    print("--- Starting API Test for /api/v1/inference/run ---")

    # --- Prepare Payload ---
    # This job_id should be from a completed training job
    training_job_id = "6d83b9a5-3911-409c-a904-80c0a81ac346"
    # input_file_s3_uri = "s3://madular-data-files/Test 2 - Raw.csv"
    # create base64 encoded file
    input_file = None
    with open(
        "/home/work/freelancer/ai_csv_to_csv_converter_DocXPress/ai_csv_to_csv_converter_DocXPress_streamlit_POC/.cursor/rules/test_csvs/test_Test 2 - Raw.csv",
        "rb",
    ) as f:
        content = f.read()
        input_file = base64.b64encode(content).decode("utf-8")

    payload = {
        "user_id": "test_user_123",
        "job_id": training_job_id,
        "input_file": input_file,
    }

    # --- Send Request ---
    try:
        print(f"Sending POST request to {BASE_URL}/inference/run")
        response = requests.post(f"{BASE_URL}/inference/run", json=payload, headers=HEADERS, timeout=30)

        # --- Print Response ---
        print(f"\nResponse Status Code: {response.status_code}")

        if response.status_code == 202:
            print("\nSuccessfully started inference job!")
            print("Response JSON:")
            print(json.dumps(response.json(), indent=2))
        else:
            print("\nError starting inference job.")
            try:
                print("Error Response JSON:")
                print(json.dumps(response.json(), indent=2))
            except json.JSONDecodeError:
                print("Could not decode JSON response.")
                print(f"Raw Response Text: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"\nAn error occurred while sending the request: {e}")

    print("\n--- Test Finished ---")


def test_list_user_jobs_endpoint():
    """Tests the /api/v1/users/{client_id}/jobs endpoint."""
    print("--- Starting API Test for /api/v1/users/{client_id}/jobs ---")
    client_id = "test_user_123"
    # --- Send Request ---
    try:
        print(f"Sending GET request to {BASE_URL}/users/{client_id}/jobs")
        response = requests.get(f"{BASE_URL}/users/{client_id}/jobs", headers=HEADERS, timeout=30)
        print(f"\nResponse Status Code: {response.status_code}")
        if response.status_code == 200:
            print("\nSuccessfully listed jobs for user!")
            print("Response JSON:")
            print(json.dumps(response.json(), indent=2))
        else:
            print("\nError listing jobs for user.")
            try:
                print("Error Response JSON:")
                print(json.dumps(response.json(), indent=2))
            except json.JSONDecodeError:
                print("Could not decode JSON response.")
                print(f"Raw Response Text: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"\nAn error occurred while sending the request: {e}")


def test_delete_user_endpoint():
    """Tests the /delete/user/{user_id} endpoint."""
    print("--- Starting API Test for /api/v1/delete/user/{user_id} ---")
    user_id = "test_user_123"
    job_id = "6d83b9a5-3911-409c-a904-80c0a81ac346"
    # --- Send Request ---
    try:
        print(f"Sending DELETE request to {BASE_URL}/delete/user/{user_id}")
        response = requests.delete(f"{BASE_URL}/delete/user/{user_id}", headers=HEADERS, timeout=30)
        print(f"\nResponse Status Code: {response.status_code}")
        if response.status_code == 204:
            print("\nSuccessfully deleted job folder!")
            print("Response JSON:")
            print(json.dumps(response.json(), indent=2))
        else:
            print("\nError deleting job folder.")
            try:
                print("Error Response JSON:")
                print(json.dumps(response.json(), indent=2))
            except json.JSONDecodeError:
                print("Could not decode JSON response.")
                print(f"Raw Response Text: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"\nAn error occurred while sending the request: {e}")


if __name__ == "__main__":
    # test_training_endpoint()

    # test_inference_endpoint()

    # test_list_user_jobs_endpoint()

    test_delete_user_endpoint()
