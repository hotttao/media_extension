# PATCH /api/products/{id}

**Resource:** [products](../resources/products.md)
**PATCH products id**
**Operation ID:** `patchProductsId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [UpdateProduct](../schemas/Update/UpdateProduct.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[Product](../schemas/Product/Product.md)

