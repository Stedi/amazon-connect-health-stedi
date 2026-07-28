# Amazon Connect Health – Stedi Real-Time Eligibility

> [!WARNING]
> This is a demo implementation for testing purposes only. It has not been tested end-to-end with Amazon Connect Health. Do not use this in production.

This Lambda function is a demo integration between [Amazon Connect Health](https://aws.amazon.com/products/connect/health/) and [Stedi's Real-Time Eligibility Check API](https://www.stedi.com/docs/healthcare/api-reference/post-healthcare-eligibility). It is intended to demonstrate how Amazon Connect Health's [RTE integration](https://docs.aws.amazon.com/connecthealth/latest/userguide/insurance-verification.html) can be wired up to Stedi as the eligibility vendor. It receives eligibility verification requests from Amazon Connect Health, calls the Stedi Eligibility API, and returns a mapped response.

Adapted from the [AWS sample reference implementation](https://github.com/aws-samples/sample-healthcare-realtime-eligibility) (MIT-0).

**Reference docs:**
- [Amazon Connect Health – Insurance verification integration](https://docs.aws.amazon.com/connecthealth/latest/userguide/insurance-verification.html)
- [AWS sample reference implementation](https://github.com/aws-samples/sample-healthcare-realtime-eligibility)

## Testing

### Direct Lambda invocation

The Lambda is set up to run one of Stedi's [mock Aetna requests](https://www.stedi.com/docs/healthcare/api-reference/mock-requests-eligibility-checks#aetna---mock-request-1-1). The test event is in `events/stedi-test.json`.

The request hits Stedi's production API but returns mock data. No PII or actual patient data is returned.

Amazon Connect Health's request and response schemas have no field for a [service type code (STC)](https://www.stedi.com/docs/healthcare/eligibility-stc-procedure-codes), so both ends are hard-coded in `function/mapper.py`:

- The request asks for STC `30` (Health Benefit Plan Coverage), which returns benefits across service types.
- The response returns the first in-network co-payment for STC `33` (Chiropractic) as `expectedServiceCost`. To return a co-payment for a different service, update `COPAY_SERVICE_TYPE_CODE`.

**Prerequisites:**
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- AWS credentials configured for your target account
- A [Stedi test API key](https://www.stedi.com/docs/healthcare/api-reference#creating-an-api-key)

**1. Set your Stedi API key as an environment variable:**

Get a key from the [Stedi API keys page](https://www.stedi.com/app/settings/api-keys), then:

```bash
export STEDI_TEST_API_KEY=<YOUR_TEST_API_KEY>
```

**2. Build:**

```bash
sam build
```

**3. Deploy:**

```bash
sam deploy \
  --stack-name amazon-connect-health-stedi-rte \
  --region <YOUR_AWS_REGION> \
  --profile <YOUR_AWS_PROFILE> \
  --parameter-overrides StediApiKey=$STEDI_TEST_API_KEY \
  --capabilities CAPABILITY_IAM \
  --resolve-s3
```

> [!WARNING]
> If you use `sam deploy --guided` instead, do not save the configuration to `samconfig.toml` when prompted. The file stores parameter values in plain text, including your API key. Never commit it to source control.

**4. Get the deployed function ARN:**

```bash
sam list stack-outputs \
  --stack-name amazon-connect-health-stedi-rte \
  --region <YOUR_AWS_REGION> \
  --profile <YOUR_AWS_PROFILE>
```

Copy the `RTEVerificationFunctionArn` value from the output.

**5. Invoke the Lambda:**

```bash
aws lambda invoke \
  --function-name <RTEVerificationFunctionArn> \
  --region <YOUR_AWS_REGION> \
  --profile <YOUR_AWS_PROFILE> \
  --payload file://events/stedi-test.json \
  --cli-binary-format raw-in-base64-out \
  /dev/stdout | jq .
```

Expected response:

```json
{
  "statusCode": 200,
  "body": "{\"status\":\"ACTIVE\",\"eligibilityPeriodStart\":\"2025-01-01\",\"eligibilityPeriodEnd\":\"2025-12-31\",\"paymentInformation\":{\"expectedServiceCost\":25.0}}"
}
{
  "StatusCode": 200,
  "ExecutedVersion": "$LATEST"
}
```

**6. Tear down:**

```bash
sam delete \
  --stack-name amazon-connect-health-stedi-rte \
  --region <YOUR_AWS_REGION> \
  --profile <YOUR_AWS_PROFILE>
```

### End-to-end testing with Amazon Connect Health

To test the full integration, create an Amazon Connect Health domain and configure the Lambda as the RTE integration function.

**Prerequisites:**
- An active AWS account with [IAM Identity Center enabled](https://docs.aws.amazon.com/singlesignon/latest/userguide/get-set-up-for-idc.html) in the same region you are deploying to
- The Lambda deployed and the `RTEVerificationFunctionArn` output noted

**Steps:**

Adopted from the [Amazon Connect Health – Setting up](https://docs.aws.amazon.com/connecthealth/latest/userguide/setting-up.html) docs:

1. Open the [Create domain page](https://console.aws.amazon.com/connect-health/domains/create) in the Amazon Connect Health console (log in to AWS if prompted).
2. Under **Use case scope**, select **Agents for both**.
3. Under **Details → Name**, enter a name for your domain (e.g. `stedi-rte-test`).
4. Under **Users**, click **Add users** and enter your email address to add yourself as a user.
5. Under **Integration function → Insurance verification Lambda function ARN**, paste the `RTEVerificationFunctionArn`.
6. Under **Sample agent flow deployment → Amazon Connect instance**, choose **Create and use a new Amazon Connect instance** and enter an **Access URL** subdomain (e.g. `stedi-rte-test`).
7. Choose **Create**.

## File Structure

```
amazon-connect-health-stedi-rte/
├── template.yaml                  # SAM deployment template
├── README.md
├── events/
│   └── stedi-test.json            # Test event for local/deployed testing
└── function/
    ├── handler.py                 # Lambda entry point
    ├── rte_vendor_client.py       # Stedi API authentication and calls
    ├── mapper.py                  # Request/response field mapping
    ├── models.py                  # Pydantic models for request and response schemas
    └── requirements.txt           # Python dependencies (pydantic, requests)
```

| File | Purpose |
|---|---|
| `function/handler.py` | Lambda entry point. Validates the incoming event, delegates to the mapper and Stedi client, and returns the response. |
| `function/rte_vendor_client.py` | Reads the Stedi API key from Secrets Manager and calls the eligibility endpoint. Credentials are cached per cold start. |
| `function/mapper.py` | Transforms Amazon Connect Health request fields into the Stedi eligibility request format and maps the Stedi response back to the expected output schema. |
| `function/models.py` | Pydantic models defining the request and response contracts between Amazon Connect Health and this Lambda. |
| `function/requirements.txt` | Lists `pydantic` and `requests` as external dependencies. |


## Deployed Resources

| Resource | Type | Description |
|---|---|---|
| `VendorCredentialsKmsKey` | AWS::KMS::Key | Customer-managed KMS key with automatic rotation. Encrypts the Secrets Manager secret, Lambda environment variables, and the DLQ. |
| `VendorCredentials` | AWS::SecretsManager::Secret | Stores the Stedi API key (`{"api_key":"..."}`), encrypted with the CMK. |
| `RTEDeadLetterQueue` | AWS::SQS::Queue | Dead Letter Queue for failed Lambda invocations. Messages retained for 14 days. |
| `RTEVerificationFunction` | AWS::Serverless::Function | The Lambda function that performs eligibility verification. |
| `SecretsManagerVpcEndpoint` | AWS::EC2::VPCEndpoint | *(Conditional)* Interface VPC Endpoint for Secrets Manager. Only created when VPC parameters are provided. |

### Notes

- **Concurrency:** Capped at `ReservedConcurrentExecutions: 10`. Adjust based on expected call volume.
- **Timeout:** 30 seconds.
- **VPC Placement:** Optional. When provided, Lambda is deployed into private subnets. A NAT Gateway is required for the Lambda to reach the Stedi API.
- **Secrets Manager VPC Endpoint:** Created when `VpcId` is provided. Keeps credential retrieval traffic on the AWS private network.
- **Dead Letter Queue:** Failed asynchronous invocations land here. Monitor for operational issues.
- **KMS Encryption:** A single CMK encrypts the secret, Lambda env vars, and DLQ. Key rotation is enabled automatically.

### Outputs

| Output | Description |
|---|---|
| `RTEVerificationFunctionArn` | ARN of the RTE Verification Lambda function |

After deploying, provide the `RTEVerificationFunctionArn` value when configuring the RTE integration in Amazon Connect Health.

## Lambda Configuration

### Environment Variables

Set automatically by the SAM template.

| Variable | Description |
|---|---|
| `RTE_VENDOR_API_URL` | Stedi API base URL |
| `RTE_VENDOR_ELIGIBILITY_PATH` | Path to the eligibility endpoint (`/change/medicalnetwork/eligibility/v3`) |
| `RTE_VENDOR_CREDENTIALS_SECRET_ARN` | ARN of the Secrets Manager secret containing the Stedi API key |

### Credentials

The Stedi API key is stored in AWS Secrets Manager as `{"api_key":"..."}` and retrieved at runtime. Cached in memory for the lifetime of the Lambda execution environment (one Secrets Manager call per cold start).

### IAM Permissions

- `secretsmanager:GetSecretValue` on the Stedi credentials secret
- `kms:Decrypt` on the CMK
- VPC network interface permissions *(only when deployed in a VPC)*

## Request Schema

Amazon Connect Health sends the following JSON payload to this Lambda:

```json
{
  "coverageDetails": {
    "identifier": { "id": "string (Stedi tradingPartnerServiceId)" },
    "groupNumber": "string",
    "insuranceName": "string",
    "memberNumber": "string",
    "subscriber": {
      "name": { "givenNames": ["string"], "lastName": "string" },
      "dateOfBirth": "YYYY-MM-DD"
    }
  },
  "patientIdentifier": { "id": "string" },
  "requestPeriodStart": "YYYY-MM-DD",
  "requestPeriodEnd": "YYYY-MM-DD",
  "providerNPI": { "id": "string (10-digit NPI)" },
  "providerLastName": "string (optional, mapped to provider organizationName)",
  "departmentNPI": { "id": "string (optional, accepted but unused)" }
}
```

## Response Schema

On success (HTTP 200):

```json
{
  "statusCode": 200,
  "body": "{\"status\":\"ACTIVE\",\"eligibilityPeriodStart\":\"YYYY-MM-DD\",\"eligibilityPeriodEnd\":\"YYYY-MM-DD\",\"paymentInformation\":{\"expectedServiceCost\":null}}"
}
```

| Field | Description |
|---|---|
| `status` | `ACTIVE` if any `benefitsInformation` entry has `code: "1"`, otherwise `INACTIVE` |
| `eligibilityPeriodStart` | From `planInformation.planBeginDate`, falling back to `benefitsPeriod` dates, then `requestPeriodStart` |
| `eligibilityPeriodEnd` | From `planInformation.planEndDate`, falling back to `benefitsPeriod` dates, then `requestPeriodEnd` |
| `paymentInformation.expectedServiceCost` | `benefitAmount` from the first in-network co-payment (`code: "B"`) for service type code `33`. `null` if no match |

