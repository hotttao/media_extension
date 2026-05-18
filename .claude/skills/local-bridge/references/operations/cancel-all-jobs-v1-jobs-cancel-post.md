# POST /v1/jobs/cancel

**Resource:** [jobs](../resources/jobs.md)
**Cancel All Jobs**
**Operation ID:** `cancel_all_jobs_v1_jobs_cancel_post`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `platform` | query | any | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 422 | Validation Error |

**Success Response Schema:**

[CancelAllResponse](../schemas/Cancel/CancelAllResponse.md)

