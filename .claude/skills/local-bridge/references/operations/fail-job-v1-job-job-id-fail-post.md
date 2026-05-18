# POST /v1/job/{job_id}/fail

**Resource:** [job](../resources/job.md)
**Fail Job**
**Operation ID:** `fail_job_v1_job__job_id__fail_post`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `job_id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [FailSubmitRequest](../schemas/Fail/FailSubmitRequest.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 404 | Not Found |
| 422 | Validation Error |

**Success Response Schema:**

[SuccessResponse](../schemas/Success/SuccessResponse.md)

