# POST /api/materials/extract

**Resource:** [materials](../resources/materials.md)
**POST materials extract**
**Operation ID:** `postMaterialsExtract`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [MaterialExtractRequest](../schemas/Material/MaterialExtractRequest.md)

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

