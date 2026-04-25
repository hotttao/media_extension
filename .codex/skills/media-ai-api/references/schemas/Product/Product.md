# Product

Product.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `userId` | string | Yes |  |
| `teamId` | string | Yes |  |
| `name` | string | Yes |  |
| `targetAudience` | enum: MENS, WOMENS, KIDS | Yes |  |
| `productDetails` | string,null | Yes |  |
| `displayActions` | string,null | Yes |  |
| `tags` | string,null | Yes |  |
| `createdAt` | string (date-time) | Yes | ISO 8601 date-time string. |
| `updatedAt` | string (date-time) | Yes | ISO 8601 date-time string. |
| `images` | object[] | No |  |

## Nested Fields

### `images`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes |  |
| `productId` | string | Yes |  |
| `url` | string | Yes |  |
| `isMain` | boolean | Yes |  |
| `order` | integer | Yes |  |

