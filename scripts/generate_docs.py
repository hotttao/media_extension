#!/usr/bin/env python3
"""Generate OpenAPI and Postman documentation from the FastAPI app."""

from __future__ import annotations

import json
import pathlib
import sys

OUTPUT_DIR = pathlib.Path("docs")
OUTPUT_DIR.mkdir(exist_ok=True)


def generate_openapi_spec() -> dict:
    """Load the OpenAPI spec from the running app or import it directly."""
    # Import the app factory
    from local_bridge.main import create_app

    app = create_app()
    spec = app.openapi()
    return spec


def save_openapi(spec: dict) -> None:
    """Save OpenAPI spec as JSON and YAML."""
    # JSON
    json_path = OUTPUT_DIR / "openapi.json"
    json_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved: {json_path}")

    # YAML (manual conversion, no extra deps)
    yaml_path = OUTPUT_DIR / "openapi.yaml"
    yaml_content = _dict_to_yaml(spec)
    yaml_path.write_text(yaml_content, encoding="utf-8")
    print(f"  Saved: {yaml_path}")


def generate_postman_collection(spec: dict) -> dict:
    """Convert OpenAPI spec to Postman Collection v2.1 format."""
    info = spec.get("info", {})
    title = info.get("title", "Media AI Bridge API")
    version = info.get("version", "1.0.0")
    description = info.get("description", "")

    collection: dict[str, object] = {
        "info": {
            "name": title,
            "version": version,
            "description": description,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [
            {"key": "baseUrl", "value": "http://localhost:8765", "type": "string"}
        ],
        "item": [],
    }

    for path, path_item in spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue

            # Skip paths with no operation object
            if not isinstance(operation, dict):
                continue

            method = method.upper()
            op_id = operation.get("operationId", f"{method}_{path.replace('/', '_')}")
            summary = operation.get("summary", "")
            description_text = operation.get("description", "")

            # Request details
            request_body = operation.get("requestBody")
            parameters = operation.get("parameters", [])

            url_variable: list[dict] = []
            url_path = path
            for param in parameters:
                if param.get("in") == "path":
                    url_variable.append({"key": param["name"], "type": "string"})
                    url_path = url_path.replace("{" + param["name"] + "}", "{{" + param["name"] + "}}")

            query_params = [p for p in parameters if p.get("in") == "query"]

            # Build Postman request
            postman_request: dict[str, object] = {
                "name": summary or op_id,
                "request": {
                    "method": method,
                    "header": [
                        {"key": "Content-Type", "value": "application/json", "type": "text"},
                        {"key": "Accept", "value": "application/json", "type": "text"},
                    ],
                    "url": {
                        "raw": "{{baseUrl}}" + url_path,
                        "host": ["{{baseUrl}}"],
                        "path": url_path.strip("/").split("/") if url_path != "/" else [],
                    },
                    "description": description_text,
                },
                "response": [],
            }

            # URL path params
            if url_variable:
                postman_request["request"]["url"]["variable"] = url_variable

            # Query params
            if query_params:
                url_obj = postman_request["request"]["url"]
                if isinstance(url_obj, dict):
                    url_obj["query"] = [
                        {"key": p["name"], "value": "", "type": "text"} for p in query_params
                    ]

            # Request body
            if request_body:
                content = request_body.get("content", {})
                json_content = content.get("application/json")
                if json_content:
                    schema = json_content.get("schema", {})
                    example = _schema_to_example(schema)
                    postman_request["request"]["body"] = {
                        "mode": "raw",
                        "raw": json.dumps(example, ensure_ascii=False, indent=2),
                        "options": {"raw": {"language": "json"}},
                    }

            # Add auth header if cookie present in spec
            if "cookie" in str(operation) or "cookie" in str(request_body):
                pass  # cookies handled via browser extension

            collection["item"].append(
                {"name": summary or path, "request": postman_request, "response": []}
            )

    return collection


def save_postman(collection: dict) -> None:
    """Save Postman collection as JSON."""
    json_path = OUTPUT_DIR / "media-ai-bridge.postman_collection.json"
    json_path.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved: {json_path}")


def _dict_to_yaml(obj, indent: int = 0) -> str:
    """Simple dict-to-YAML converter."""
    lines: list[str] = []
    prefix = "  " * indent

    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{prefix}{key}:")
                lines.append(_dict_to_yaml(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}: []")
            else:
                safe_value = json.dumps(value, ensure_ascii=False) if isinstance(value, str) else value
                lines.append(f"{prefix}{key}: {safe_value}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(_dict_to_yaml(item, indent + 1))
            else:
                safe_value = json.dumps(item, ensure_ascii=False) if isinstance(item, str) else item
                lines.append(f"{prefix}- {safe_value}")
    else:
        lines.append(f"{prefix}{obj}")

    return "\n".join(lines)


def _schema_to_example(schema: dict) -> dict:
    """Generate a minimal example from a JSON Schema object."""
    example: dict = {}
    for key, value in schema.get("properties", {}).items():
        if isinstance(value, dict):
            if value.get("type") == "array":
                example[key] = []
            elif value.get("type") == "object":
                example[key] = _schema_to_example(value)
            elif "example" in value:
                example[key] = value["example"]
            elif "default" in value:
                example[key] = value["default"]
            else:
                example[key] = None
        else:
            example[key] = None
    return example


def main() -> int:
    print(f"Generating API documentation in {OUTPUT_DIR}/ ...")

    spec = generate_openapi_spec()
    save_openapi(spec)

    collection = generate_postman_collection(spec)
    save_postman(collection)

    print("\nDone. Generated files:")
    for f in sorted(OUTPUT_DIR.glob("*")):
        if f.is_file():
            size = len(f.read_bytes())
            print(f"  {f.name} ({size} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())