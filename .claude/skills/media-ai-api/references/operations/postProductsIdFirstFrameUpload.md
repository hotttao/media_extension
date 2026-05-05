# POST /api/products/{id}/first-frame-upload

**Resource:** [products](../resources/products.md)
**POST products id first frame upload**
**Operation ID:** `postProductsIdFirstFrameUpload`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `multipart/form-data`

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

[FirstFrameUploadResponse](../schemas/First/FirstFrameUploadResponse.md)

