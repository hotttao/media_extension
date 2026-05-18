# GET /v1/job/claim

**Resource:** [job](../resources/job.md)
**Claim Job**
**Operation ID:** `claim_job_v1_job_claim_get`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `platform` | query | any | No |  |
| `x-worker-id` | header | any | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 422 | Validation Error |

**Success Response Schema:**

[ClaimResponse](../schemas/Claim/ClaimResponse.md)

