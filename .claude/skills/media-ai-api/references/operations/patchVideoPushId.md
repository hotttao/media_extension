# PATCH /api/video-push/{id}

**Resource:** [video-push](../resources/video-push.md)
**PATCH video push id**
**Operation ID:** `patchVideoPushId`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `id` | path | string | Yes |  |

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [VideoPushUpdate](../schemas/Video/VideoPushUpdate.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |
| 404 | Error |
| 500 | Error |

**Success Response Schema:**

[VideoPushResponse](../schemas/Video/VideoPushResponse.md)

