# Material

Material asset.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `userId` | string,null | Yes |  |
| `teamId` | string,null | Yes |  |
| `visibility` | enum: PUBLIC, PERSONAL, TEAM | Yes |  |
| `type` | enum: SCENE, POSE, MAKEUP... | Yes |  |
| `name` | string | Yes |  |
| `description` | string,null | Yes |  |
| `url` | string | Yes |  |
| `tags` | string,null | Yes |  |
| `createdAt` | string (date-time) | Yes | ISO 8601 date-time string. |
| `updatedAt` | string (date-time) | Yes | ISO 8601 date-time string. |

