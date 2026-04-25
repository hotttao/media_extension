# POST /api/products/{id}/first-frame

**Resource:** [products](../resources/products.md)
**POST products id first frame**
**Operation ID:** `postProductsIdFirstFrame`

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
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[FirstFrameSaveResponse](../schemas/First/FirstFrameSaveResponse.md)

