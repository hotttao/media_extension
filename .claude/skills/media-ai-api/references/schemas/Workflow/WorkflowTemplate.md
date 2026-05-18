# WorkflowTemplate

Workflow template response.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `virtualIpId` | string | Yes |  |
| `name` | string | Yes |  |
| `poseId` | string | Yes |  |
| `sceneId` | string | Yes |  |
| `createdAt` | string (date-time) | Yes | ISO 8601 date-time string. |
| `updatedAt` | string (date-time) | Yes | ISO 8601 date-time string. |
| `movements` | object[] | No |  |

## Nested Fields

### `movements`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `movementId` | string | Yes |  |

