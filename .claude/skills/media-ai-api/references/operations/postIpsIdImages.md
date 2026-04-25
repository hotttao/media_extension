# POST /api/ips/{id}/images

**Resource:** [ips](../resources/ips.md)
**POST ips id images**
**Operation ID:** `postIpsIdImages`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

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

[VirtualIp](../schemas/Virtual/VirtualIp.md)

