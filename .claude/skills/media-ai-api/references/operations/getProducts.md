# GET /api/products

**Resource:** [products](../resources/products.md)
**GET products**
**Operation ID:** `getProducts`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `targetAudience` | query | enum: MENS, WOMENS, KIDS | No | Filter products by target audience. |
| `search` | query | string | No | Keyword used to search product names and metadata. |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[ProductList](../schemas/Product/ProductList.md)

