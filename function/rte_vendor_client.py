"""
Stedi Eligibility API Client.

Handles authentication and API calls to the Stedi Real-Time Eligibility API.
API key is read from Secrets Manager (format: {"api_key": "..."}).
Credentials are cached per cold start to avoid redundant Secrets Manager calls.

Environment Variables:
    RTE_VENDOR_API_URL                - Stedi Eligibility API base URL
    RTE_VENDOR_ELIGIBILITY_PATH       - Path to eligibility endpoint
    RTE_VENDOR_CREDENTIALS_SECRET_ARN - Secrets Manager ARN for Stedi API key
"""

import json
import os

import boto3
import requests

# Credentials cache — fetched once per cold start
_cached_credentials: dict | None = None


def _require_env(name: str) -> str:
    """Get a required environment variable or raise."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is not set")
    return value


def _get_api_key() -> str:
    """Fetch the Stedi API key from Secrets Manager."""
    global _cached_credentials

    if _cached_credentials:
        return _cached_credentials["api_key"]

    secret_arn = _require_env("RTE_VENDOR_CREDENTIALS_SECRET_ARN")

    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=secret_arn)
    _cached_credentials = json.loads(resp["SecretString"])
    return _cached_credentials["api_key"]


def check_eligibility(vendor_request: dict) -> dict:
    """Calls the Stedi eligibility API."""
    api_key = _get_api_key()
    api_url = _require_env("RTE_VENDOR_API_URL")
    eligibility_path = _require_env("RTE_VENDOR_ELIGIBILITY_PATH")

    print("Calling Stedi eligibility API")

    response = requests.post(
        f"{api_url}{eligibility_path}",
        json=vendor_request,
        headers={
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(f"Stedi API returned status {response.status_code}: {response.text}")

    return response.json()
