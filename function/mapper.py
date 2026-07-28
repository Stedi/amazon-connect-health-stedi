"""
Field mapping between Amazon Connect Health and Stedi's Real-Time Eligibility API.

Handles:
- Amazon Connect Health request → Stedi request transformation
- Stedi response → Amazon Connect Health response transformation
"""

from models import (
    RTEVerificationRequest,
    RTEVerificationResponse,
    PaymentInformation,
)


def _to_stedi_date(iso_date: str) -> str:
    """Converts YYYY-MM-DD to YYYYMMDD."""
    return iso_date.replace("-", "")


def _from_stedi_date(stedi_date: str) -> str:
    """Converts YYYYMMDD to YYYY-MM-DD."""
    return f"{stedi_date[0:4]}-{stedi_date[4:6]}-{stedi_date[6:8]}"


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
    if subscriber_name and subscriber_name.given_names:
        subscriber_dict["firstName"] = subscriber_name.given_names[0]
    if subscriber_name and subscriber_name.last_name:
        subscriber_dict["lastName"] = subscriber_name.last_name
    if subscriber and subscriber.date_of_birth:
        subscriber_dict["dateOfBirth"] = _to_stedi_date(subscriber.date_of_birth)

    provider_dict: dict = {"npi": request.provider_npi.id}
    if request.provider_last_name:
        provider_dict["organizationName"] = request.provider_last_name

    return {
        "tradingPartnerServiceId": request.coverage_details.identifier.id,
        "provider": provider_dict,
        "subscriber": subscriber_dict,
        "encounter": {
            "serviceTypeCodes": ["30"],
        },
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
    benefits = vendor_response.get("benefitsInformation") or []
    plan_info = vendor_response.get("planInformation") or {}

    # status: ACTIVE if any benefitsInformation entry has code "1"
    status = "INACTIVE"
    for benefit in benefits:
        if benefit.get("code") == "1":
            status = "ACTIVE"
            break

    # eligibility period from planInformation
    begin_date = plan_info.get("planBeginDate")
    end_date = plan_info.get("planEndDate")

    # fallback: scan benefitsInformation[].benefitsPeriod
    if not begin_date or not end_date:
        for benefit in benefits:
            period = benefit.get("benefitsPeriod") or {}
            if not begin_date:
                begin_date = period.get("beginDate")
            if not end_date:
                end_date = period.get("endDate")
            if begin_date and end_date:
                break

    # expectedServiceCost: benefitAmount from first in-network Co-Payment for service type "33"
    # (Chiropractic). Could be made configurable via env var or Lambda input to support multiple STCs.
    COPAY_SERVICE_TYPE_CODE = "33"
    expected_service_cost = None
    for benefit in benefits:
        if (
            benefit.get("code") == "B"
            and benefit.get("inPlanNetworkIndicatorCode") == "Y"
            and COPAY_SERVICE_TYPE_CODE in (benefit.get("serviceTypeCodes") or [])
        ):
            raw_amount = benefit.get("benefitAmount")
            if raw_amount is not None:
                expected_service_cost = float(raw_amount)
                break

    return RTEVerificationResponse(
        status=status,
        eligibilityPeriodStart=(
            _from_stedi_date(begin_date)
            if begin_date
            else original_request.request_period_start
        ),
        eligibilityPeriodEnd=(
            _from_stedi_date(end_date)
            if end_date
            else original_request.request_period_end
        ),
        paymentInformation=PaymentInformation(expectedServiceCost=expected_service_cost),
    )
