# GET /v1/job/watch

**Resource:** [job](../resources/job.md)
**Watch Jobs**
**Operation ID:** `watch_jobs_v1_job_watch_get`

SSE endpoint to watch job status changes.
No polling needed - server pushes events on status changes.

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `job_id` | query | any | No | Filter events for specific job |
| `platform` | query | any | No | Filter events for specific platform |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 422 | Validation Error |

