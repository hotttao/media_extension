# PATCH /api/materials/{id}

**Resource:** [materials](../resources/materials.md)
**PATCH materials id**
**Operation ID:** `patchMaterialsId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [UpdateMaterial](../schemas/Update/UpdateMaterial.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[Material](../schemas/Material/Material.md)

