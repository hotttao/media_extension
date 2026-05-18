# GET /api/virtual-ips/{ipId}/workflow-templates/{templateId}

**Resource:** [virtual-ips](../resources/virtual-ips.md)
**GET virtual ips ipId workflow templates templateId**
**Operation ID:** `getVirtualIpsIpIdWorkflowTemplatesTemplateId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `ipId` | path | string | Yes |  |
| `templateId` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[WorkflowTemplate](../schemas/Workflow/WorkflowTemplate.md)

