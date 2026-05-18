# PATCH /api/virtual-ips/{ipId}/workflow-templates/{templateId}

**Resource:** [virtual-ips](../resources/virtual-ips.md)
**PATCH virtual ips ipId workflow templates templateId**
**Operation ID:** `patchVirtualIpsIpIdWorkflowTemplatesTemplateId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `ipId` | path | string | Yes |  |
| `templateId` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [WorkflowTemplateUpdate](../schemas/Workflow/WorkflowTemplateUpdate.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[WorkflowTemplate](../schemas/Workflow/WorkflowTemplate.md)

