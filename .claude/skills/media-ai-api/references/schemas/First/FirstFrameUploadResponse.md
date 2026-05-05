# FirstFrameUploadResponse

First frame upload with alternative images response.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | boolean | Yes |  |
| `count` | number | Yes |  |
| `results` | object[] | Yes |  |

## Nested Fields

### `results`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `index` | number | Yes |  |
| `firstFrameId` | string | Yes |  |
| `firstFrameUrl` | string | Yes |  |
| `alternativeId` | string | Yes |  |
| `status` | enum: created, existing | Yes |  |

