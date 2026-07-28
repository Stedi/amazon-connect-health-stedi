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

_PLAN_DATE_FIELDS = ("planBegin", "planEnd", "plan")

# Benefit type codes 1-5 mean active coverage, 6-8 mean inactive coverage.
# https://www.stedi.com/docs/healthcare/eligibility-active-coverage-benefits#active-and-inactive-coverage
_ACTIVE_CODES = frozenset({"1", "2", "3", "4", "5"})
_INACTIVE_CODES = frozenset({"6", "7", "8"})


def _coverage_status(benefits: list) -> str:
    """ACTIVE, INACTIVE, or UNKNOWN when the payer reported neither.

    A payer that returns no benefits, or only a `V` (Cannot Process) stub
    returns UNKNOWN.
    """
    codes = {benefit.get("code") for benefit in benefits}
    if codes & _ACTIVE_CODES:
        return "ACTIVE"
    if codes & _INACTIVE_CODES:
        return "INACTIVE"
    return "UNKNOWN"


def _plan_period(dates: dict) -> tuple[str | None, str | None]:
    """(begin, end) from planDateInformation, in field priority order.

    Returns YYYYMMDD strings, which compare correctly as strings.
    """
    begins: list[str] = []
    ends: list[str] = []

    for field in _PLAN_DATE_FIELDS:
        value = dates.get(field)
        if not value:
            continue
        begin, _, end = value.partition("-")
        # A lone date is a beginning, except in planEnd, where it's an ending.
        if field == "planEnd" and not end:
            ends.append(begin)
            continue
        begins.append(begin)
        if end:
            ends.append(end)

    begin = begins[0] if begins else None
    end = ends[0] if ends else None

    # Never report a period that ends before it starts.
    if begin and end and end < begin:
        end = None

    return begin, end


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
            "beginningDateOfService": _to_stedi_date(request.request_period_start),
            "endDateOfService": _to_stedi_date(request.request_period_end),
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

    begin_date, end_date = _plan_period(vendor_response.get("planDateInformation") or {})

    return RTEVerificationResponse(
        status=_coverage_status(benefits),
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
