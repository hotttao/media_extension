# GET /api/products/{id}

**Resource:** [products](../resources/products.md)
**GET products id**
**Operation ID:** `getProductsId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[Product](../schemas/Product/Product.md)

