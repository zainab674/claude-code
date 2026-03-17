"""
OpenAPI spec export and Postman collection generator.

GET /openapi/spec        → raw OpenAPI 3.0 JSON
GET /openapi/postman     → Postman Collection v2.1 JSON
GET /openapi/swagger-ui  → redirect to /docs (built-in)
"""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from utils.auth import get_current_user

router = APIRouter(prefix="/openapi", tags=["openapi"])


@router.get("/spec")
async def get_openapi_spec(request: Request):
    """Download the raw OpenAPI 3.0 JSON spec."""
    app = request.app
    spec = app.openapi()
    return JSONResponse(
        content=spec,
        headers={"Content-Disposition": 'attachment; filename="payrollos-api.json"'},
    )


@router.get("/postman")
async def get_postman_collection(request: Request):
    """
    Generate a Postman Collection v2.1 from the OpenAPI spec.
    Import this file directly into Postman.
    """
    app = request.app
    spec = app.openapi()
    base_url = str(request.base_url).rstrip("/")
    collection = _build_postman_collection(spec, base_url)
    return JSONResponse(
        content=collection,
        headers={"Content-Disposition": 'attachment; filename="payrollos-postman.json"'},
    )


def _build_postman_collection(spec: dict, base_url: str) -> dict:
    """Convert OpenAPI spec to Postman Collection v2.1."""
    info = spec.get("info", {})
    paths = spec.get("paths", {})

    # Group endpoints by tag
    tag_groups: dict = {}
    for path, methods in paths.items():
        for method, operation in methods.items():
            if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            tags = operation.get("tags", ["General"])
            tag = tags[0] if tags else "General"
            if tag not in tag_groups:
                tag_groups[tag] = []

            # Build request body
            body = None
            req_body = operation.get("requestBody", {})
            if req_body:
                content = req_body.get("content", {})
                json_content = content.get("application/json", {})
                schema = json_content.get("schema", {})
                example = _schema_to_example(schema, spec)
                body = {
                    "mode": "raw",
                    "raw": json.dumps(example, indent=2),
                    "options": {"raw": {"language": "json"}},
                }

            # Build URL with path params highlighted
            url_path = path
            url_vars = []
            for param in operation.get("parameters", []):
                if param.get("in") == "path":
                    url_vars.append({
                        "key": param["name"],
                        "value": f"<{param['name']}>",
                        "description": param.get("description", ""),
                    })
            query_params = [
                {
                    "key": p["name"],
                    "value": "",
                    "description": p.get("description", ""),
                    "disabled": not p.get("required", False),
                }
                for p in operation.get("parameters", [])
                if p.get("in") == "query"
            ]

            item = {
                "name": operation.get("summary", f"{method.upper()} {path}"),
                "request": {
                    "method": method.upper(),
                    "header": [
                        {"key": "Content-Type", "value": "application/json"},
                        {"key": "Authorization", "value": "Bearer {{token}}", "type": "text"},
                    ],
                    "url": {
                        "raw": f"{{{{base_url}}}}{url_path}",
                        "host": ["{{base_url}}"],
                        "path": [p for p in url_path.split("/") if p],
                        "variable": url_vars,
                        "query": query_params,
                    },
                    "description": operation.get("description", ""),
                },
            }
            if body:
                item["request"]["body"] = body

            tag_groups[tag].append(item)

    # Build folder structure
    folders = [
        {
            "name": tag.replace("-", " ").title(),
            "item": items,
        }
        for tag, items in sorted(tag_groups.items())
    ]

    return {
        "info": {
            "name": info.get("title", "PayrollOS API"),
            "description": info.get("description", ""),
            "version": info.get("version", "1.0.0"),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [
            {"key": "base_url", "value": base_url, "type": "string"},
            {"key": "token", "value": "", "type": "string",
             "description": "JWT access token — get from POST /auth/login"},
        ],
        "auth": {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}],
        },
        "event": [
            {
                "listen": "prerequest",
                "script": {
                    "type": "text/javascript",
                    "exec": [
                        "// Auto-refresh token logic can go here",
                        "// pm.collectionVariables.set('token', pm.environment.get('jwt_token'));"
                    ],
                },
            }
        ],
        "item": folders,
        "_postman_collection_generated": datetime.utcnow().isoformat() + "Z",
    }


def _schema_to_example(schema: dict, spec: dict, depth: int = 0) -> dict:
    """Generate a realistic example JSON body from an OpenAPI schema."""
    if depth > 4:
        return {}
    if not schema:
        return {}

    # Resolve $ref
    if "$ref" in schema:
        ref = schema["$ref"].replace("#/components/schemas/", "")
        schema = spec.get("components", {}).get("schemas", {}).get(ref, {})

    schema_type = schema.get("type", "object")
    example = schema.get("example")
    if example is not None:
        return example

    if schema_type == "object":
        props = schema.get("properties", {})
        required = schema.get("required", [])
        result = {}
        for key, prop_schema in props.items():
            if key in required or depth == 0:
                result[key] = _schema_to_example(prop_schema, spec, depth + 1)
        return result

    if schema_type == "array":
        items = schema.get("items", {})
        return [_schema_to_example(items, spec, depth + 1)]

    # Scalar defaults
    fmt = schema.get("format", "")
    if schema_type == "string":
        if fmt == "date": return "2026-01-01"
        if fmt == "date-time": return "2026-01-01T00:00:00Z"
        if fmt == "email": return "user@example.com"
        if fmt == "password": return "string"
        if "enum" in schema: return schema["enum"][0]
        return schema.get("default", "string")
    if schema_type in ("integer", "number"):
        return schema.get("default", schema.get("minimum", 0))
    if schema_type == "boolean":
        return schema.get("default", False)
    return None
