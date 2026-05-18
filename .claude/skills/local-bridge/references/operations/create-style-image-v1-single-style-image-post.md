# POST /v1/single/style-image

**Resource:** [single](../resources/single.md)
**Create Style Image**
**Operation ID:** `create_style_image_v1_single_style_image_post`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [StyleImageCreateRequest](../schemas/Style/StyleImageCreateRequest.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 400 | Bad Request |
| 404 | Not Found |
| 422 | Validation Error |

**Success Response Schema:**

[StyleImageCreatedResponse](../schemas/Style/StyleImageCreatedResponse.md)

