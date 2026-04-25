# GET /api/materials/{id}

**Resource:** [materials](../resources/materials.md)
**GET materials id**
**Operation ID:** `getMaterialsId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[Material](../schemas/Material/Material.md)

