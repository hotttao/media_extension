# POST /api/auth/callback/credentials

**Resource:** [auth](../resources/auth.md)
**POST NextAuth credentials login**
**Operation ID:** `postAuthCallbackCredentials`

## Request Body

**Required:** Yes

**Content Types:** `application/x-www-form-urlencoded`

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Unauthorized |

**Success Response Schema:**

[CredentialsLoginResponse](../schemas/Credentials/CredentialsLoginResponse.md)

