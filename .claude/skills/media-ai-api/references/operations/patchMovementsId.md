# PATCH /api/movements/{id}

**Resource:** [movements](../resources/movements.md)
**PATCH movements id**
**Operation ID:** `patchMovementsId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [UpdateMovementMaterial](../schemas/Update/UpdateMovementMaterial.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[MovementMaterial](../schemas/Movement/MovementMaterial.md)

