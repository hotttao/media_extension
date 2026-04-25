# POST /api/materials/ip/{ipId}

**Resource:** [materials](../resources/materials.md)
**POST materials ip ipId**
**Operation ID:** `postMaterialsIpIpId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `ipId` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `multipart/form-data`

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[IpMaterial](../schemas/Ip/IpMaterial.md)

