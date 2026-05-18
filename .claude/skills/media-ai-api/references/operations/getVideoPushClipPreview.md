# GET /api/video-push/clip-preview

**Resource:** [video-push](../resources/video-push.md)
**GET video push clip preview**
**Operation ID:** `getVideoPushClipPreview`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `productId` | query | string | No |  |
| `ipId` | query | string | No |  |
| `sceneId` | query | string | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[VideoPushClipPreview](../schemas/Video/VideoPushClipPreview.md)

