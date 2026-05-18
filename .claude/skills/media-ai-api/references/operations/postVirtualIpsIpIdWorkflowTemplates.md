# POST /api/virtual-ips/{ipId}/workflow-templates

**Resource:** [virtual-ips](../resources/virtual-ips.md)
**POST virtual ips ipId workflow templates**
**Operation ID:** `postVirtualIpsIpIdWorkflowTemplates`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `ipId` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [WorkflowTemplateCreate](../schemas/Workflow/WorkflowTemplateCreate.md)

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

[WorkflowTemplate](../schemas/Workflow/WorkflowTemplate.md)

