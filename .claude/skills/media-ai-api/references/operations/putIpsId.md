# PUT /api/ips/{id}

**Resource:** [ips](../resources/ips.md)
**PUT ips id**
**Operation ID:** `putIpsId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [UpdateVirtualIp](../schemas/Update/UpdateVirtualIp.md)

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

