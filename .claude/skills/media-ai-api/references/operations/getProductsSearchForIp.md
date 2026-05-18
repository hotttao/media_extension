# GET /api/products/search-for-ip

**Resource:** [products](../resources/products.md)
**GET products search for ip**
**Operation ID:** `getProductsSearchForIp`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `ipId` | query | string | No |  |
| `filter` | query | string | No |  |
| `search` | query | string | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[SuccessResponse](../schemas/Success/SuccessResponse.md)

