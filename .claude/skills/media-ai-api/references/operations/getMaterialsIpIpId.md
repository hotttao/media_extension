# GET /api/materials/ip/{ipId}

**Resource:** [materials](../resources/materials.md)
**GET materials ip ipId**
**Operation ID:** `getMaterialsIpIpId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `ipId` | path | string | Yes |  |
| `type` | query | string | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[IpMaterialList](../schemas/Ip/IpMaterialList.md)

