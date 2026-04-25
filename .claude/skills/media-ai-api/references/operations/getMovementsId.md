# GET /api/movements/{id}

**Resource:** [movements](../resources/movements.md)
**GET movements id**
**Operation ID:** `getMovementsId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[Movement](../schemas/Movement/Movement.md)

