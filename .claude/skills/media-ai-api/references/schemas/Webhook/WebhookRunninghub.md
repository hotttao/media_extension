# WebhookRunninghub

RunningHub webhook callback payload.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `taskId` | string | Yes |  |
| `status` | enum: SUCCESS, FAILED | No |  |
| `results` | object[] | No |  |
| `errorMessage` | string | No |  |

## Nested Fields

### `results`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | Yes |  |

