# POST /v1/single/model-image

**Resource:** [single](../resources/single.md)
**Create Model Image**
**Operation ID:** `create_model_image_v1_single_model_image_post`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [ModelImageCreateRequest](../schemas/Model/ModelImageCreateRequest.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Successful Response |
| 400 | Bad Request |
| 404 | Not Found |
| 422 | Validation Error |

**Success Response Schema:**

[ModelImageCreatedResponse](../schemas/Model/ModelImageCreatedResponse.md)

