# POST /api/user/api-keys

**Resource:** [user](../resources/user.md)
**POST user api keys**
**Operation ID:** `postUserKeys`

## Request Body

**Required:** Yes

**Content Types:** `application/json`

**Schema:** [ApiKeyCreate](../schemas/Api/ApiKeyCreate.md)

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

