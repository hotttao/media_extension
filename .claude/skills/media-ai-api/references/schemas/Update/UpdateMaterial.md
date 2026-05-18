# UpdateMaterial

Payload for partially updating a material asset.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `visibility` | enum: PUBLIC, PERSONAL, TEAM | No | Who can access this material. |
| `type` | enum: SCENE, POSE, MAKEUP... | No | Material category used for filtering and generation workflows. |
| `name` | string | No | Human-readable material name. |
| `description` | string | No | Optional notes describing the material usage or style. |
| `prompt` | string | No | Optional prompt text used to guide later generation workflows. |
| `tags` | string[] | No | Searchable labels attached to the material. |
| `url` | string | No | Public or internal URL of the material asset. |

