# GET /api/products/{id}/first-frames

**Resource:** [products](../resources/products.md)
**GET products id first frames**
**Operation ID:** `getProductsIdFirstFrames`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |
| `ipId` | query | string | No |  |
| `styleImageId` | query | string | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[FirstFrameList](../schemas/First/FirstFrameList.md)

