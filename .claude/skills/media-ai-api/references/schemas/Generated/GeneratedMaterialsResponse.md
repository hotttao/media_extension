# GeneratedMaterialsResponse

Generated product materials grouped by type.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `modelImages` | object[] | Yes |  |
| `styleImages` | object[] | Yes |  |
| `firstFrames` | object[] | Yes |  |

## Nested Fields

### `modelImages`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `productId` | string | Yes |  |
| `ipId` | string | Yes |  |
| `url` | string | Yes |  |
| `prompt` | string,null | Yes |  |
| `inputHash` | string | Yes |  |
| `createdAt` | string (date-time) | Yes | ISO 8601 date-time string. |

### `styleImages`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `productId` | string | Yes |  |
| `ipId` | string | Yes |  |
| `modelImageId` | string | Yes |  |
| `url` | string | Yes |  |
| `prompt` | string,null | Yes |  |
| `poseId` | string,null | Yes |  |
| `makeupId` | string,null | Yes |  |
| `accessoryId` | string,null | Yes |  |
| `inputHash` | string | Yes |  |
| `createdAt` | string (date-time) | Yes | ISO 8601 date-time string. |

### `firstFrames`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `productId` | string | Yes |  |
| `ipId` | string | Yes |  |
| `styleImageId` | string,null | Yes |  |
| `url` | string | Yes |  |
| `prompt` | string,null | Yes |  |
| `sceneId` | string,null | Yes |  |
| `composition` | string,null | Yes |  |
| `inputHash` | string | Yes |  |
| `createdAt` | string (date-time) | Yes | ISO 8601 date-time string. |

