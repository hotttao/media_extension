# POST /api/ips

**Resource:** [ips](../resources/ips.md)
**POST ips**
**Operation ID:** `postIps`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [CreateVirtualIp](../schemas/Create/CreateVirtualIp.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[VirtualIp](../schemas/Virtual/VirtualIp.md)

