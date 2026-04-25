# RegisterResponse

Registration response.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user` | object | Yes | User account returned by the API. |

## Nested Fields

### `user`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `email` | string | Yes |  |
| `nickname` | string,null | Yes |  |
| `teamId` | string,null | Yes |  |
| `role` | enum: ADMIN, MEMBER | Yes |  |

