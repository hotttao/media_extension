# GET /api/products/{id}/first-frame

**Resource:** [products](../resources/products.md)
**GET products id first frame**
**Operation ID:** `getProductsIdFirstFrame`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |
| `ipId` | query | string | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[FirstFrameSaveResponse](../schemas/First/FirstFrameSaveResponse.md)

