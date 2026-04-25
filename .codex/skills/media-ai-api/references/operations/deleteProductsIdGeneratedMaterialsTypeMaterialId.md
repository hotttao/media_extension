# DELETE /api/products/{id}/generated-materials/{type}/{materialId}

**Resource:** [products](../resources/products.md)
**DELETE products id generated materials type materialId**
**Operation ID:** `deleteProductsIdGeneratedMaterialsTypeMaterialId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |
| `type` | path | string | Yes |  |
| `materialId` | path | string | Yes |  |

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

