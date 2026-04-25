# DELETE /api/products/{id}/images/{imageId}

**Resource:** [products](../resources/products.md)
**DELETE products id images imageId**
**Operation ID:** `deleteProductsIdImagesImageId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |
| `imageId` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[SuccessResponse](../schemas/Success/SuccessResponse.md)

