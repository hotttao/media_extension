# MaterialFilter

Query filters for listing materials.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | enum: SCENE, POSE, MAKEUP... | No | Filter materials by category. |
| `visibility` | enum: PUBLIC, PERSONAL, TEAM | No | Filter materials by visibility scope. |
| `search` | string | No | Keyword used to search material names and metadata. |

