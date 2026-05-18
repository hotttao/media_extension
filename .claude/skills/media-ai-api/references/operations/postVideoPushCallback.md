# POST /api/video-push/callback

**Resource:** [video-push](../resources/video-push.md)
**POST video push callback**
**Operation ID:** `postVideoPushCallback`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `videoPushId` | query | string | No |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [VideoPushCallback](../schemas/Video/VideoPushCallback.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[SuccessResponse](../schemas/Success/SuccessResponse.md)

