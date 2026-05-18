# VideoPushBatchUpdate

Batch update request payload.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `updates` | object[] | Yes |  |

## Nested Fields

### `updates`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `videoPushId` | string | Yes |  |
| `thumbnail` | string | No |  |
| `title` | string | No |  |
| `content` | string | No |  |
| `isQualified` | boolean | No |  |
| `isPublished` | boolean | No |  |
| `manualClipUrl` | string | No |  |

