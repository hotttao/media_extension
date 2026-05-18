# VideoPushResponse

VideoPush record.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `videoId` | string | Yes |  |
| `videoIdHash` | string | Yes |  |
| `productId` | string | Yes |  |
| `ipId` | string,null | Yes |  |
| `sceneId` | string | Yes |  |
| `templateName` | string,null | Yes |  |
| `musicId` | string,null | Yes |  |
| `url` | string | Yes |  |
| `thumbnail` | string,null | Yes |  |
| `title` | string,null | Yes |  |
| `content` | string,null | Yes |  |
| `manualClipUrl` | string,null | Yes |  |
| `status` | enum: pending, completed, failed... | Yes |  |
| `isQualified` | boolean | Yes |  |
| `isPublished` | boolean | Yes |  |
| `createdAt` | string (date-time) | Yes | ISO 8601 date-time string. |
| `updatedAt` | string (date-time) | Yes | ISO 8601 date-time string. |

