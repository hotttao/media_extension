# POST /v1/job/{job_id}/requeue

**Resource:** [job](../resources/job.md)
**Requeue Job**
**Operation ID:** `requeue_job_v1_job__job_id__requeue_post`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `job_id` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 404 | Not Found |
| 422 | Validation Error |

**Success Response Schema:**

[RequeueResponse](../schemas/Requeue/RequeueResponse.md)

