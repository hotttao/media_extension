# VideoTask

Video generation task.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `userId` | string | Yes |  |
| `teamId` | string | Yes |  |
| `workflowId` | string | Yes |  |
| `ipId` | string,null | Yes |  |
| `status` | enum: PENDING, RUNNING, COMPLETED... | Yes |  |
| `params` | string,null | Yes |  |
| `result` | string,null | Yes |  |
| `error` | string,null | Yes |  |
| `startedAt` | string,null (date-time) | Yes | ISO 8601 date-time string. |
| `completedAt` | string,null (date-time) | Yes | ISO 8601 date-time string. |
| `createdAt` | string (date-time) | Yes | ISO 8601 date-time string. |

