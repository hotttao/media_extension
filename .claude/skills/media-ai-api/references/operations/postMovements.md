# POST /api/movements

**Resource:** [movements](../resources/movements.md)
**POST movements**
**Operation ID:** `postMovements`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [CreateMovementMaterial](../schemas/Create/CreateMovementMaterial.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[MovementMaterial](../schemas/Movement/MovementMaterial.md)

