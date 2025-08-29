# AI CSV Converter

AI-powered CSV to CSV converter using CrewAI agents

## API Endpoints

### `POST /api/v1/train`

**Summary:** Start Training Job

**Description:** Starts a new training job, uploads files to S3, and kicks off the conversion workflow.

**Security:** Requires `X-API-KEY` header.

**Request Body:**

```json
{
  "user_id": "string",
  "input_file": "string",
  "expected_output_file": "string",
  "job_title": "string",
  "description": "string | null",
  "owner": "string",
  "general_instructions": "string | null",
  "column_instructions": {
    "additionalProperties": "string"
  }
}
```

**Responses:**

*   `202 Accepted`: Successful Response (ConversionJobResponse)
*   `422 Unprocessable Entity`: Validation Error (HTTPValidationError)

### `POST /api/v1/inference/run`

**Summary:** Run Inference Job

**Description:** Runs an inference job using a specified trained model and input file.

**Security:** Requires `X-API-KEY` header.

**Request Body:**

```json
{
  "user_id": "string",
  "job_id": "string",
  "input_file": "string"
}
```

**Responses:**

*   `202 Accepted`: Successful Response (ConversionJobResponse)
*   `422 Unprocessable Entity`: Validation Error (HTTPValidationError)

### `GET /api/v1/users/{client_id}/jobs`

**Summary:** List all jobs for a user

**Description:** Get a list of all jobs for a specific user by reading metadata from S3.

**Security:** Requires `X-API-KEY` header.

**Parameters:**

*   `client_id` (path): string

**Responses:**

*   `200 OK`: Successful Response (List of job metadata dictionaries)
*   `422 Unprocessable Entity`: Validation Error (HTTPValidationError)

### `GET /`

**Summary:** Root

**Description:** Root endpoint - redirects to API documentation.

**Responses:**

*   `200 OK`: Successful Response

### `GET /health`

**Summary:** Health Check

**Description:** Health check endpoint.

**Responses:**

*   `200 OK`: Successful Response

## How to Run the Application

1.  **Set up your environment variables:**

    Create a `.env` file in the root directory of the project with the following content:

    ```
    OPENAI_API_KEY=your_openai_api_key
    AWS_ACCESS_KEY_ID=your_aws_access_key_id
    AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
    AWS_BUCKET_NAME=your_s3_bucket_name
    FASTAPI_AND_WEP_APP_SECRET_KEY=your_secret_api_key
    ```

    Replace the placeholder values with your actual keys and bucket name.

2.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

    (Note: You might need to create a `requirements.txt` file first if it doesn't exist. You can generate it using `pip freeze > requirements.txt`)

3.  **Run the application:**

    ```bash
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    ```

    Or, if you are running it from the `main.py` file directly:

    ```bash
    python main.py
    ```

    The API documentation will be available at `http://localhost:8000/docs`.

## How to Run Tests

```bash
pytest
```

(Note: Ensure you have `pytest` installed: `pip install pytest`)
