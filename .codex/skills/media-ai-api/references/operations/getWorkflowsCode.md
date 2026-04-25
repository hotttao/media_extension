# GET /api/workflows/{code}

**Resource:** [workflows](../resources/workflows.md)
**GET workflows code**
**Operation ID:** `getWorkflowsCode`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `code` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[Workflow](../schemas/Workflow/Workflow.md)

