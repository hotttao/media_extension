# POST /api/products/{id}/model-image/save

**Resource:** [products](../resources/products.md)
**POST products id model image save**
**Operation ID:** `postProductsIdModelImageSave`

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

[ModelImageSaveResponse](../schemas/Model/ModelImageSaveResponse.md)

