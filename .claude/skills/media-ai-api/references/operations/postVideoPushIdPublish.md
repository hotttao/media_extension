# POST /api/video-push/{id}/publish

**Resource:** [video-push](../resources/video-push.md)
**POST video push id publish**
**Operation ID:** `postVideoPushIdPublish`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [VideoPushPublish](../schemas/Video/VideoPushPublish.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[SuccessResponse](../schemas/Success/SuccessResponse.md)

