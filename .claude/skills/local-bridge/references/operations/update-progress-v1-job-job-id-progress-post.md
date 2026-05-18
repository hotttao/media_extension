# POST /v1/job/{job_id}/progress

**Resource:** [job](../resources/job.md)
**Update Progress**
**Operation ID:** `update_progress_v1_job__job_id__progress_post`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `job_id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [ProgressUpdateRequest](../schemas/Progress/ProgressUpdateRequest.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 404 | Not Found |
| 422 | Validation Error |

**Success Response Schema:**

[SuccessResponse](../schemas/Success/SuccessResponse.md)

