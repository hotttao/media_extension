# POST /api/movement-materials

**Resource:** [movement-materials](../resources/movement-materials.md)
**POST movement materials**
**Operation ID:** `postMovementMaterials`

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

