# POST /api/products

**Resource:** [products](../resources/products.md)
**POST products**
**Operation ID:** `postProducts`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [CreateProduct](../schemas/Create/CreateProduct.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[Product](../schemas/Product/Product.md)

