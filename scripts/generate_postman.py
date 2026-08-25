#!/usr/bin/env python3
"""Convert OpenAPI 3.0 schema to Postman Collection v2.1."""

import json


def _generate_example(schema: dict, components: dict) -> any:
    if not schema:
        return {}

    ref = schema.get("$ref")
    if ref:
        ref_name = ref.split("/")[-1]
        schema = components.get(ref_name, schema)

    schema_type = schema.get("type")

    if schema_type == "object":
        return {
            k: _generate_example(v, components) for k, v in schema.get("properties", {}).items()
        }
    elif schema_type == "array":
        items = schema.get("items", {})
        return [_generate_example(items, components)]
    elif schema_type == "string":
        if schema.get("format") == "email":
            return "user@example.com"
        if schema.get("format") == "date-time":
            return "2024-01-01T00:00:00Z"
        return "string"
    elif schema_type == "integer":
        return 1
    elif schema_type == "boolean":
        return True

    return {}


def _build_request(path: str, method: str, details: dict, base_url: str, openapi: dict) -> dict:
    headers = []
    request_body = None

    if "requestBody" in details:
        content = details["requestBody"].get("content", {})
        if "application/json" in content:
            schema = content["application/json"].get("schema", {})
            example = _generate_example(schema, openapi.get("components", {}).get("schemas", {}))
            request_body = {
                "mode": "raw",
                "raw": json.dumps(example, indent=2) if example else "{}",
                "options": {"raw": {"language": "json"}},
            }

    if method in ("post", "put", "patch"):
        headers.append({"key": "Content-Type", "value": "application/json", "type": "text"})

    url_parts = path.strip("/").split("/")
    url_dict = {
        "raw": base_url + path,
        "host": [base_url.replace("https://", "").replace("http://", "").split("/")[0]],
        "path": url_parts,
    }

    item = {
        "name": f"{method.upper()} {path}",
        "request": {
            "method": method.upper(),
            "header": headers,
            "url": url_dict,
            "description": details.get("description", ""),
        },
        "response": [],
    }

    if request_body:
        item["request"]["body"] = request_body

    for param in details.get("parameters", []):
        if param.get("in") == "header":
            item["request"]["header"].append({"key": param["name"], "value": "", "type": "text"})

    return item


def main():
    with open("openapi.json") as f:
        openapi = json.load(f)

    base_url = openapi.get("servers", [{"url": "http://localhost:8000"}])[0]["url"]
    info = openapi.get("info", {})

    collection = {
        "info": {
            "name": info.get("title", "API Collection"),
            "description": info.get("description", ""),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [{"key": "baseUrl", "value": base_url, "type": "string"}],
        "item": [],
    }

    for path, methods in openapi.get("paths", {}).items():
        for method, details in methods.items():
            if method.lower() in ("get", "post", "put", "patch", "delete"):
                item = _build_request(path, method.lower(), details, base_url, openapi)
                if item:
                    collection["item"].append(item)

    with open("TaskFlow_Postman_Collection.json", "w") as f:
        json.dump(collection, f, indent=2)

    print(f"Generated Postman collection with {len(collection['item'])} requests")


if __name__ == "__main__":
    main()
