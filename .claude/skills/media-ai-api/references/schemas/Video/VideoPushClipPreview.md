# VideoPushClipPreview

Clip preview response.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `groups` | object[] | Yes |  |
| `totalClippable` | number | Yes |  |
| `videoCount` | number | Yes |  |
| `hasMusic` | boolean | Yes |  |

## Nested Fields

### `groups`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `videoIdHash` | string | Yes |  |
| `videoIds` | string | Yes |  |
| `potentialClips` | number | Yes |  |
| `existingPending` | number | Yes |  |
| `existingCompleted` | number | Yes |  |
| `clippable` | number | Yes |  |

