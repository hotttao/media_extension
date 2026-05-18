# GET /api/products/{id}/videos

**Resource:** [products](../resources/products.md)
**GET products id videos**
**Operation ID:** `getProductsIdVideos`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |
| `movementId` | query | string | No |  |
| `poseId` | query | string | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[VideoSummaryList](../schemas/Video/VideoSummaryList.md)

