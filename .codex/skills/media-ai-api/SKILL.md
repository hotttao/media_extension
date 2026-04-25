---
name: media-ai-api
description: . Use when working with the Media AI API or when the user needs to interact with this API.
metadata:
  api-version: "0.1.0"
  openapi-version: "3.1.0"
---

# Media AI API

## How to Use This Skill

This API documentation is split into multiple files for on-demand loading.

**Directory structure:**
```
references/
├── resources/      # 12 resource index files
├── operations/     # 54 operation detail files
└── schemas/        # 22 schema groups, 42 schema files
```

**Navigation flow:**
1. Find the resource you need in the list below
2. Read `references/resources/<resource>.md` to see available operations
3. Read `references/operations/<operation>.md` for full details
4. If an operation references a schema, read `references/schemas/<prefix>/<schema>.md`

## Base URL

- `http://localhost:3000` - Local development server

## Resources

- **products** → `references/resources/products.md` (20 ops)
- **materials** → `references/resources/materials.md` (7 ops)
- **ips** → `references/resources/ips.md` (6 ops)
- **movements** → `references/resources/movements.md` (5 ops)
- **auth** → `references/resources/auth.md` (3 ops)
- **workflows** → `references/resources/workflows.md` (3 ops)
- **movement-materials** → `references/resources/movement-materials.md` (2 ops)
- **tasks** → `references/resources/tasks.md` (2 ops)
- **teams** → `references/resources/teams.md` (2 ops)
- **tools** → `references/resources/tools.md` (2 ops)
- **upload** → `references/resources/upload.md` (1 ops)
- **webhooks** → `references/resources/webhooks.md` (1 ops)
