# AlternativeImageList

Alternative image list response.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `alternatives` | object[] | Yes |  |

## Nested Fields

### `alternatives`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `materialType` | enum: MODEL_IMAGE, STYLE_IMAGE, FIRST_FRAME... | Yes |  |
| `relatedId` | string | Yes |  |
| `url` | string | Yes |  |
| `source` | enum: AI_GENERATED, USER_UPLOADED | Yes |  |
| `isConfirmed` | boolean | Yes |  |
| `createdAt` | string (date-time) | Yes | ISO 8601 date-time string. |

