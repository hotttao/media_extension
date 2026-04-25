# GET /api/tasks/{id}

**Resource:** [tasks](../resources/tasks.md)
**GET tasks id**
**Operation ID:** `getTasksId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 403 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[VideoTask](../schemas/Video/VideoTask.md)

