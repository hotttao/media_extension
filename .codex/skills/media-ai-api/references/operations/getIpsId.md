# GET /api/ips/{id}

**Resource:** [ips](../resources/ips.md)
**GET ips id**
**Operation ID:** `getIpsId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[VirtualIp](../schemas/Virtual/VirtualIp.md)

