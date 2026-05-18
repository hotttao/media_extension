# POST /v1/job/{job_id}/cancel

**Resource:** [job](../resources/job.md)
**Cancel Job**
**Operation ID:** `cancel_job_v1_job__job_id__cancel_post`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `job_id` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 404 | Not Found |
| 409 | Conflict |
| 422 | Validation Error |

**Success Response Schema:**

[CancelResponse](../schemas/Cancel/CancelResponse.md)

