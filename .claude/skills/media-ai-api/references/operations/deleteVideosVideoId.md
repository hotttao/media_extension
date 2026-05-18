# DELETE /api/videos/{videoId}

**Resource:** [videos](../resources/videos.md)
**DELETE videos videoId**
**Operation ID:** `deleteVideosVideoId`

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

[SuccessResponse](../schemas/Success/SuccessResponse.md)

