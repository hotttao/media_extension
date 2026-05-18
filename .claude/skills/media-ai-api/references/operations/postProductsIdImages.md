# POST /api/products/{id}/images

**Resource:** [products](../resources/products.md)
**POST products id images**
**Operation ID:** `postProductsIdImages`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [ProductImageCreate](../schemas/Product/ProductImageCreate.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[ProductImage](../schemas/Product/ProductImage.md)

