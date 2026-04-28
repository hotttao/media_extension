# GET /api/videos/{videoId}

**Resource:** [videos](../resources/videos.md)
**GET videos videoId**
**Operation ID:** `getVideosVideoId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `videoId` | path | string | Yes |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[VideoDetail](../schemas/Video/VideoDetail.md)

