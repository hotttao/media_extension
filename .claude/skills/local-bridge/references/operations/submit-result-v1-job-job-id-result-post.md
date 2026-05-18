# POST /v1/job/{job_id}/result

**Resource:** [job](../resources/job.md)
**Submit Result**
**Operation ID:** `submit_result_v1_job__job_id__result_post`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `job_id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [ResultSubmitRequest](../schemas/Result/ResultSubmitRequest.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 404 | Not Found |
| 422 | Validation Error |

**Success Response Schema:**

[ResultSubmitResponse](../schemas/Result/ResultSubmitResponse.md)

