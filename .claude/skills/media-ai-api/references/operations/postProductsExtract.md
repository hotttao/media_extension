# POST /api/products/extract

**Resource:** [products](../resources/products.md)
**POST products extract**
**Operation ID:** `postProductsExtract`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [ExtractProductInfo](../schemas/Extract/ExtractProductInfo.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[GenerationJobResponse](../schemas/Generation/GenerationJobResponse.md)

