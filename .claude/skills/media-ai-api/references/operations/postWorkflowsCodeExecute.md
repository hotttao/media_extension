# POST /api/workflows/{code}/execute

**Resource:** [workflows](../resources/workflows.md)
**POST workflows code execute**
**Operation ID:** `postWorkflowsCodeExecute`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `code` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[VideoTask](../schemas/Video/VideoTask.md)

