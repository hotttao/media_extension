# POST /v1/jobs

**Resource:** [jobs](../resources/jobs.md)
**Create Jobs**
**Operation ID:** `create_jobs_v1_jobs_post`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [JobsCreateRequest](../schemas/Jobs/JobsCreateRequest.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 400 | Bad Request |
| 422 | Validation Error |

**Success Response Schema:**

[JobCreatedResponse](../schemas/Job/JobCreatedResponse.md)

