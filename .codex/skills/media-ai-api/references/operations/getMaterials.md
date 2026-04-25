# GET /api/materials

**Resource:** [materials](../resources/materials.md)
**GET materials**
**Operation ID:** `getMaterials`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `type` | query | enum: SCENE, POSE, MAKEUP... | No | Filter materials by category. |
| `search` | query | string | No | Keyword used to search material names and metadata. |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[MaterialList](../schemas/Material/MaterialList.md)

