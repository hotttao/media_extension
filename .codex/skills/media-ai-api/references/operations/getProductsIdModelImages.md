# GET /api/products/{id}/model-images

**Resource:** [products](../resources/products.md)
**GET products id model images**
**Operation ID:** `getProductsIdModelImages`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |
| `ipId` | query | string | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[ModelImageList](../schemas/Model/ModelImageList.md)

