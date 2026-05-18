# POST /api/tools/image-blend

**Resource:** [tools](../resources/tools.md)
**POST tools image blend**
**Operation ID:** `postToolsImageBlend`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [ImageBlendRequest](../schemas/Image/ImageBlendRequest.md)

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[GenerationJobResponse](../schemas/Generation/GenerationJobResponse.md)

