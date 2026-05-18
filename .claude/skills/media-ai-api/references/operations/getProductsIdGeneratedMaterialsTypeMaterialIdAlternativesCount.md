# GET /api/products/{id}/generated-materials/{type}/{materialId}/alternatives-count

**Resource:** [products](../resources/products.md)
**GET products id generated materials type materialId alternatives count**
**Operation ID:** `getProductsIdGeneratedMaterialsTypeMaterialIdAlternativesCount`

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
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[SuccessResponse](../schemas/Success/SuccessResponse.md)

