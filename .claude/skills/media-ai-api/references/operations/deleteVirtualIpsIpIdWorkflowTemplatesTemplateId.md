# DELETE /api/virtual-ips/{ipId}/workflow-templates/{templateId}

**Resource:** [virtual-ips](../resources/virtual-ips.md)
**DELETE virtual ips ipId workflow templates templateId**
**Operation ID:** `deleteVirtualIpsIpIdWorkflowTemplatesTemplateId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `ipId` | path | string | Yes |  |
| `templateId` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 204 | Success |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[SuccessResponse](../schemas/Success/SuccessResponse.md)

