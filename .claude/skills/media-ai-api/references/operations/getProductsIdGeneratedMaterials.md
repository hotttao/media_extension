# GET /api/products/{id}/generated-materials

**Resource:** [products](../resources/products.md)
**GET products id generated materials**
**Operation ID:** `getProductsIdGeneratedMaterials`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |
| `ipId` | query | string | No |  |
| `where` | query | string | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[GeneratedMaterialsResponse](../schemas/Generated/GeneratedMaterialsResponse.md)

