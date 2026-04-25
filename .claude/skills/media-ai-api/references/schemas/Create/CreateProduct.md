# CreateProduct

Payload for creating a product.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Product display name. |
| `targetAudience` | enum: MENS, WOMENS, KIDS | Yes | Primary customer segment for this product. |
| `productDetails` | string | No | Free-form product details, selling points, fabric, fit, or usage context. |
| `displayActions` | string | No | Desired presentation actions or poses for generated product media. |
| `tags` | string[] | No | Searchable labels attached to the product. |
| `images` | object[] | No | Images associated with the product. |

## Nested Fields

### `images`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | Yes | Image URL. |
| `isMain` | boolean | No | Whether this image is the primary product image. |
| `order` | integer | No | Sort order for product images. |

