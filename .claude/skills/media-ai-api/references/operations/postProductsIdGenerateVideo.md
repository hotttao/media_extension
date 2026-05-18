# POST /api/products/{id}/generate-video

**Resource:** [products](../resources/products.md)
**POST products id generate video**
**Operation ID:** `postProductsIdGenerateVideo`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [GenerateVideoRequest](../schemas/Generate/GenerateVideoRequest.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[VideoGenerationResponse](../schemas/Video/VideoGenerationResponse.md)

