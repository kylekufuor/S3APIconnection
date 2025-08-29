import requests
import base64
import json

# --- Configuration ---
BASE_URL = "http://localhost:8000/api/v1"

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
        response = requests.post(f"{BASE_URL}/train", json=payload, timeout=30)

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


if __name__ == "__main__":
    test_training_endpoint()
