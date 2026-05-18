# POST /api/products/{id}/style-image/save

**Resource:** [products](../resources/products.md)
**POST products id style image save**
**Operation ID:** `postProductsIdStyleImageSave`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [StyleImageSaveRequest](../schemas/Style/StyleImageSaveRequest.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[StyleImageSaveResponse](../schemas/Style/StyleImageSaveResponse.md)

