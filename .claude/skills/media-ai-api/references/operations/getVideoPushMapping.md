# GET /api/video-push/mapping

**Resource:** [video-push](../resources/video-push.md)
**GET video push mapping**
**Operation ID:** `getVideoPushMapping`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `productId` | query | string | No |  |
| `ipId` | query | string | No |  |
| `videoIds` | query | string | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |

**Success Response Schema:**

[SuccessResponse](../schemas/Success/SuccessResponse.md)

