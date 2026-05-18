# DELETE /api/daily-publish-plan/assign-ip

**Resource:** [daily-publish-plan](../resources/daily-publish-plan.md)
**DELETE daily publish plan assign ip**
**Operation ID:** `deleteDailyPublishPlanAssignIp`

## Parameters

| Name | In | Type | Required | Description |
|------|------|------|----------|-------------|
| `productId` | query | string | No |  |
| `ipId` | query | string | No |  |

## Responses

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Error |
| 401 | Error |
| 500 | Error |

**Success Response Schema:**

[SuccessResponse](../schemas/Success/SuccessResponse.md)

