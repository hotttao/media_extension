# VideoDetail

Complete video detail payload.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `name` | string,null | No |  |
| `url` | string | Yes |  |
| `thumbnail` | string,null | No |  |
| `prompt` | string,null | No |  |
| `createdAt` | string (date-time) | Yes | ISO 8601 date-time string. |
| `product` | object,null | No |  |
| `ip` | object,null | No |  |
| `task` | object,null | No | Task summary returned with a video record. |
| `trace` | object,null | No | Resolved generation trace resources for a video. |
| `relatedVideos` | object[] | Yes |  |

## Nested Fields

### `relatedVideos`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `name` | string,null | No |  |
| `url` | string | Yes |  |
| `thumbnail` | string,null | No |  |
| `prompt` | string,null | No |  |
| `createdAt` | string (date-time) | Yes | ISO 8601 date-time string. |
| `product` | object,null | No |  |
| `ip` | object,null | No |  |
| `task` | object,null | No | Task summary returned with a video record. |
| `trace` | object,null | No | Resolved generation trace resources for a video. |

