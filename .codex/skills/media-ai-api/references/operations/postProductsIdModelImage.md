# POST /api/products/{id}/model-image

**Resource:** [products](../resources/products.md)
**POST products id model image**
**Operation ID:** `postProductsIdModelImage`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

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

