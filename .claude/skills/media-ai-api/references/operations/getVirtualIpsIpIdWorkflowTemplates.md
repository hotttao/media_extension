# GET /api/virtual-ips/{ipId}/workflow-templates

**Resource:** [virtual-ips](../resources/virtual-ips.md)
**GET virtual ips ipId workflow templates**
**Operation ID:** `getVirtualIpsIpIdWorkflowTemplates`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `ipId` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[WorkflowTemplateList](../schemas/Workflow/WorkflowTemplateList.md)

