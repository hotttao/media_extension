# POST /v1/single/first-frame-image

**Resource:** [single](../resources/single.md)
**Create First Frame Image**
**Operation ID:** `create_first_frame_image_v1_single_first_frame_image_post`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [FirstFrameImageCreateRequest](../schemas/First/FirstFrameImageCreateRequest.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 400 | Bad Request |
| 404 | Not Found |
| 422 | Validation Error |

**Success Response Schema:**

[FirstFrameImageCreatedResponse](../schemas/First/FirstFrameImageCreatedResponse.md)

