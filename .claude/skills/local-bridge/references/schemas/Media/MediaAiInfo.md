# MediaAiInfo

Job sidecar media-ai metadata. Fields vary by job kind.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `kind` | any | No | Job kind: first-frame-image, style-image, model-image, video |
| `platform` | any | No | Execution platform: jimeng or gpt |
| `baseUrl` | any | No | Media AI service base URL |
| `productId` | any | No | Product ID on Media AI platform |
| `productName` | any | No | Product display name |
| `ipId` | any | No | IP/character ID |
| `styleImageId` | any | No | 定妆图 ID (for first-frame-image with jimeng) |
| `styleImageUrl` | any | No | 定妆图 URL |
| `sceneId` | any | No | 场景 ID (for first-frame-image with jimeng) |
| `sceneName` | any | No | 场景名称 |
| `sceneUrl` | any | No | 场景图片 URL |
| `uploadSubDir` | any | No | Upload subdirectory on Media AI |
| `firstFrameId` | any | No | 首帧图 ID (for video) |
| `firstFrameUrl` | any | No | 首帧图 URL |
| `movement` | any | No | 动作描述 (for video) |
| `modelImageId` | any | No | 模特图 ID (for style-image/model-image) |
| `poseId` | any | No | 姿势 ID (for style-image) |

