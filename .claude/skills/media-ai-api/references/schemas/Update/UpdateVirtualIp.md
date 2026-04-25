# UpdateVirtualIp

Payload for partially updating a virtual IP character.

**Type:** object

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `nickname` | string | No | Display name for the virtual IP character. |
| `avatarUrl` | string | No | Avatar image URL. |
| `fullBodyUrl` | string | No | Full-body image URL. |
| `threeViewUrl` | string | No | Three-view reference image URL. |
| `nineViewUrl` | string | No | Nine-view reference image URL. |
| `age` | integer | No | Character age in years. |
| `gender` | enum: MALE, FEMALE, OTHER | No | Character gender. |
| `height` | number | No | Character height. |
| `weight` | number | No | Character weight. |
| `bust` | number | No | Bust measurement. |
| `waist` | number | No | Waist measurement. |
| `hip` | number | No | Hip measurement. |
| `education` | string | No | Education background. |
| `major` | string | No | Academic major or specialty. |
| `city` | string | No | City associated with the character. |
| `occupation` | string | No | Occupation or professional role. |
| `basicSetting` | string | No | Core background setting for the character. |
| `personality` | string | No | Personality traits and behavior style. |
| `catchphrase` | string | No | Signature phrase or verbal style. |
| `smallHabit` | string | No | Small habits that make the character recognizable. |
| `familyBackground` | string | No | Family background or origin story. |
| `incomeLevel` | string | No | Income level or consumption profile. |
| `hobbies` | string | No | Hobbies and interests. |

