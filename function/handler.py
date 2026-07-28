"""
AWS Lambda handler for Real Time Eligibility (RTE) Insurance Verification.

Entry point for the Lambda function. Receives requests from Amazon Connect Health,
delegates to the vendor client, and returns mapped responses.
"""

import json
from typing import Any

from models import RTEVerificationRequest, RTEVerificationResponse
from mapper import map_request_to_vendor, map_vendor_response
from rte_vendor_client import check_eligibility
from pydantic import ValidationError


def handler(event: dict, context: Any) -> dict:
    """Main Lambda handler."""
    print("RTE Verification Request received")

    # Validate and parse request using Pydantic model
    try:
        request = RTEVerificationRequest(**event)
    except ValidationError as e:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "Validation failed",
                "details": e.errors(),
            }),
        }

    try:
        # Map incoming request to vendor format
        vendor_request = map_request_to_vendor(request)

        # Call vendor API
        vendor_response = check_eligibility(vendor_request)

        # Map vendor response back to expected format
        rte_response = map_vendor_response(vendor_response, request)

        return {
            "statusCode": 200,
            "body": rte_response.model_dump_json(by_alias=True),
        }

    except Exception as e:
        print(f"RTE Verification failed: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "RTE verification failed",
                "message": str(e),
            }),
        }
