# PUT /api/products/{id}/scenes

**Resource:** [products](../resources/products.md)
**PUT products id scenes**
**Operation ID:** `putProductsIdScenes`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [ScenesUpdate](../schemas/Scenes/ScenesUpdate.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[SuccessResponse](../schemas/Success/SuccessResponse.md)

