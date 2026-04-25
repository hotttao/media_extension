# POST /api/materials

**Resource:** [materials](../resources/materials.md)
**POST materials**
**Operation ID:** `postMaterials`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [CreateMaterial](../schemas/Create/CreateMaterial.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[Material](../schemas/Material/Material.md)

