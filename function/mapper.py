"""
Field mapping between Amazon Connect Health and Stedi's Real-Time Eligibility Check JSON API.

Handles:
- Amazon Connect Health request → Stedi request transformation
- Stedi response → Amazon Connect Health response transformation
"""

from models import (
    RTEVerificationRequest,
    RTEVerificationResponse,
    PaymentInformation,
)


def _coverage_status(statuses: list) -> str:
    """ACTIVE, INACTIVE, or UNKNOWN when the payer reported neither.

    A payer that returns no coverage statuses returns UNKNOWN.
    https://www.stedi.com/docs/healthcare/eligibility-active-coverage-benefits#active-and-inactive-coverage
    """
    values = {entry.get("status") or "" for entry in statuses}
    if any(value.startswith("ACTIVE") for value in values):
        return "ACTIVE"
    if any(value.startswith("INACTIVE") for value in values):
        return "INACTIVE"
    return "UNKNOWN"


def _benefits(vendor_response: dict, benefit_type: str) -> list:
    return [
        entry
        for plan in vendor_response.get("plans") or []
        for entry in (plan.get("benefits") or {}).get(benefit_type) or []
    ]


def _plan_period(vendor_response: dict) -> tuple[str | None, str | None]:
    """(start, end) of the subscriber's plan dates, as YYYY-MM-DD strings."""
    plan = ((vendor_response.get("subscriber") or {}).get("dates") or {}).get("plan") or {}
    start, end = plan.get("start"), plan.get("end")

    # Never report a period that ends before it starts.
    if start and end and end < start:
        end = None

    return start, end


def map_request_to_vendor(request: RTEVerificationRequest) -> dict:
    """
    Maps an Amazon Connect Health request to the Stedi eligibility request format.

    Args:
        request: Validated request model from Amazon Connect Health.

    Returns:
        Dict in the Stedi eligibility request format.
    """
    subscriber = request.coverage_details.subscriber
    subscriber_name = subscriber.name if subscriber else None

    subscriber_dict: dict = {"memberId": request.coverage_details.member_number}
    if subscriber and subscriber.date_of_birth:
        subscriber_dict["dateOfBirth"] = subscriber.date_of_birth
    person: dict = {}
    if subscriber_name and subscriber_name.given_names:
        person["firstName"] = subscriber_name.given_names[0]
    if subscriber_name and subscriber_name.last_name:
        person["lastName"] = subscriber_name.last_name
    if person:
        subscriber_dict["name"] = {"person": person}

    return {
        "encounter": {
            "dates": {
                "service": {
                    "end": request.request_period_end,
                    "start": request.request_period_start,
                }
            },
            "services": [{"system": "STC", "value": "30"}],
        },
        "payerId": request.coverage_details.identifier.id,
        "provider": {"npi": request.provider_npi.id},
        "subscriber": subscriber_dict,
    }


def map_vendor_response(
    vendor_response: dict, original_request: RTEVerificationRequest
) -> RTEVerificationResponse:
    """
    Maps the Stedi eligibility response to the Amazon Connect Health response format.

    Args:
        vendor_response: Raw response from the Stedi eligibility API.
        original_request: The original validated request (for fallback values).

    Returns:
        RTEVerificationResponse model.
    """
    # expectedServiceCost: amount from first in-network co-payment for service type "33"
    # (Chiropractic). Could be made configurable via env var or Lambda input to support multiple STCs.
    COPAY_SERVICE_TYPE_CODE = "33"
    expected_service_cost = None
    for copay in _benefits(vendor_response, "coPayment"):
        service = copay.get("service") or {}
        if (
            (copay.get("network") or {}).get("indicator") == "IN_NETWORK"
            and service.get("system") == "STC"
            and service.get("value") == COPAY_SERVICE_TYPE_CODE
        ):
            raw_amount = copay.get("amount")
            if raw_amount is not None:
                expected_service_cost = float(raw_amount)
                break

    start_date, end_date = _plan_period(vendor_response)

    return RTEVerificationResponse(
        status=_coverage_status(_benefits(vendor_response, "statuses")),
        eligibilityPeriodStart=start_date or original_request.request_period_start,
        eligibilityPeriodEnd=end_date or original_request.request_period_end,
        paymentInformation=PaymentInformation(expectedServiceCost=expected_service_cost),
    )
