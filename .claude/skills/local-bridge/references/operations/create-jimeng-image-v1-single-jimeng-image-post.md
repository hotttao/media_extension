# POST /v1/single/jimeng-image

**Resource:** [single](../resources/single.md)
**Create Jimeng Image**
**Operation ID:** `create_jimeng_image_v1_single_jimeng_image_post`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [JimengImageCreateRequest](../schemas/Jimeng/JimengImageCreateRequest.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 400 | Bad Request |
| 404 | Not Found |
| 422 | Validation Error |

**Success Response Schema:**

[JimengImageCreatedResponse](../schemas/Jimeng/JimengImageCreatedResponse.md)

