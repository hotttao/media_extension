# POST /api/video-push/batch-update

**Resource:** [video-push](../resources/video-push.md)
**POST video push batch update**
**Operation ID:** `postVideoPushBatchUpdate`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [VideoPushBatchUpdate](../schemas/Video/VideoPushBatchUpdate.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[SuccessResponse](../schemas/Success/SuccessResponse.md)

