# CreateMaterial

Payload for creating a material asset.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `visibility` | enum: PUBLIC, PERSONAL, TEAM | Yes | Who can access this material. |
| `type` | enum: SCENE, POSE, MAKEUP... | Yes | Material category used for filtering and generation workflows. |
| `name` | string | Yes | Human-readable material name. |
| `description` | string | No | Optional notes describing the material usage or style. |
| `url` | string | Yes | Public or internal URL of the material asset. |
| `tags` | string[] | No | Searchable labels attached to the material. |

