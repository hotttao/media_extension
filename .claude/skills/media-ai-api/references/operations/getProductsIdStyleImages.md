# GET /api/products/{id}/style-images

**Resource:** [products](../resources/products.md)
**GET products id style images**
**Operation ID:** `getProductsIdStyleImages`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |
| `ipId` | query | string | No |  |
| `modelImageId` | query | string | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[StyleImageList](../schemas/Style/StyleImageList.md)

