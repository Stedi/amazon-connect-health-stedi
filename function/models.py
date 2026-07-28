"""
Pydantic models for the RTE Insurance Verification Lambda.

Defines the request and response contracts between Amazon Connect Health
and this Lambda function.
"""

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, StringConstraints

DateString = Annotated[
    str, StringConstraints(pattern=r"^(19|20)\d{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
]


class IdType(BaseModel):
    """Identifier with an ID and optional type."""

    id: str
    type: Optional[str] = None


class HumanName(BaseModel):
    """Human name structure."""

    given_names: List[str] = Field(default_factory=list, alias="givenNames")
    last_name: Optional[str] = Field(default=None, alias="lastName")

    class Config:
        populate_by_name = True


class Subscriber(BaseModel):
    """Subscriber demographics and relationship to the patient."""

    identifier: Optional[IdType] = None
    name: Optional[HumanName] = None
    date_of_birth: Optional[DateString] = Field(default=None, alias="dateOfBirth")
    relationship_to_patient: Optional[str] = Field(default=None, alias="relationshipToPatient")

    class Config:
        populate_by_name = True


class CoverageDetails(BaseModel):
    """Insurance coverage information."""

    identifier: IdType
    group_number: str = Field(alias="groupNumber")
    insurance_name: str = Field(alias="insuranceName")
    member_number: str = Field(alias="memberNumber")
    subscriber: Optional[Subscriber] = None

    class Config:
        populate_by_name = True


class PaymentInformation(BaseModel):
    """Payment information returned in the response."""

    expected_service_cost: Optional[float] = Field(default=None, alias="expectedServiceCost")

    class Config:
        populate_by_name = True


class RTEVerificationRequest(BaseModel):
    """Request model for RTE insurance verification.

    Represents the payload sent by Amazon Connect Health to this Lambda.
    """

    coverage_details: CoverageDetails = Field(alias="coverageDetails")
    patient_identifier: IdType = Field(alias="patientIdentifier")
    request_period_start: DateString = Field(alias="requestPeriodStart")
    request_period_end: DateString = Field(alias="requestPeriodEnd")
    provider_npi: IdType = Field(alias="providerNPI")
    provider_last_name: Optional[str] = Field(default=None, alias="providerLastName")
    department_npi: Optional[IdType] = Field(default=None, alias="departmentNPI")

    class Config:
        populate_by_name = True


class RTEVerificationResponse(BaseModel):
    """Response model for RTE insurance verification.

    Represents the payload this Lambda returns to Amazon Connect Health.
    """

    status: str
    eligibility_period_start: DateString = Field(alias="eligibilityPeriodStart")
    eligibility_period_end: DateString = Field(alias="eligibilityPeriodEnd")
    payment_information: Optional[PaymentInformation] = Field(
        default=None, alias="paymentInformation"
    )

    class Config:
        populate_by_name = True
