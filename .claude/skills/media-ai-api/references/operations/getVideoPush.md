# GET /api/video-push

**Resource:** [video-push](../resources/video-push.md)
**GET video push**
**Operation ID:** `getVideoPush`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `productId` | query | string | No |  |
| `ipId` | query | string | No |  |
| `qualified` | query | string | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[VideoPushListResponse](../schemas/Video/VideoPushListResponse.md)

