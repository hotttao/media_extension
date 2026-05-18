# DELETE /v1/job/{job_id}

**Resource:** [job](../resources/job.md)
**Delete Job**
**Operation ID:** `delete_job_v1_job__job_id__delete`

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

[DeleteResponse](../schemas/Delete/DeleteResponse.md)

