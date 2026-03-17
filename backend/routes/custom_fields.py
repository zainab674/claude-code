import uuid
from datetime import datetime
from typing import Optional, Any, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import CustomFieldSchema, CustomFieldValue
from utils.auth import get_current_user
from uuid import UUID

router = APIRouter(prefix="/custom-fields", tags=["custom-fields"])

ENTITY_TYPES = ["employee", "job", "pay_run", "contractor", "candidate"]
FIELD_TYPES = ["text", "number", "date", "boolean", "select", "multiselect", "url", "email"]


class FieldSchemaCreate(BaseModel):
    entity_type: str
    field_name: str
    display_name: str
    field_type: str
    options: List[str] = []
    required: bool = False
    description: Optional[str] = None
    sort_order: int = 0


@router.get("/schema")
async def list_schemas(
    entity_type: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {
        "company_id": current_user["company_id"],
        "is_active": True,
    }
    if entity_type:
        query["entity_type"] = entity_type
    
    schemas = await CustomFieldSchema.find(query).sort("entity_type", "sort_order").to_list()
    return [_ser_schema(s) for s in schemas]


@router.post("/schema", status_code=201)
async def create_schema(
    body: FieldSchemaCreate,
    current_user: dict = Depends(get_current_user),
):
    if body.entity_type not in ENTITY_TYPES:
        raise HTTPException(400, f"entity_type must be: {', '.join(ENTITY_TYPES)}")
    if body.field_type not in FIELD_TYPES:
        raise HTTPException(400, f"field_type must be: {', '.join(FIELD_TYPES)}")

    # Validate field_name is snake_case
    if not all(c.isalnum() or c == '_' for c in body.field_name):
        raise HTTPException(400, "field_name must contain only letters, numbers, and underscores")

    company_id = current_user["company_id"]

    # Check for duplicate
    existing = await CustomFieldSchema.find_one(
        CustomFieldSchema.company_id == company_id,
        CustomFieldSchema.entity_type == body.entity_type,
        CustomFieldSchema.field_name == body.field_name,
    )
    if existing:
        raise HTTPException(409, f"Field '{body.field_name}' already exists for {body.entity_type}")

    schema = CustomFieldSchema(
        company_id=company_id,
        entity_type=body.entity_type,
        field_name=body.field_name,
        display_name=body.display_name,
        field_type=body.field_type,
        options=body.options,
        required=body.required,
        description=body.description,
        sort_order=str(body.sort_order),
    )
    await schema.insert()
    return _ser_schema(schema)


@router.delete("/schema/{schema_id}", status_code=204)
async def delete_schema(
    schema_id: str,
    current_user: dict = Depends(get_current_user),
):
    schema = await CustomFieldSchema.find_one(
        CustomFieldSchema.id == UUID(schema_id),
        CustomFieldSchema.company_id == current_user["company_id"],
    )
    if not schema:
        raise HTTPException(404, "Field schema not found")
    schema.is_active = False
    await schema.save()


@router.get("/values/{entity_type}/{entity_id}")
async def get_values(
    entity_type: str,
    entity_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get all custom field values for a specific entity."""
    company_id = current_user["company_id"]
    
    schemas = await CustomFieldSchema.find(
        CustomFieldSchema.company_id == company_id,
        CustomFieldSchema.entity_type == entity_type,
        CustomFieldSchema.is_active == True,
    ).sort("sort_order").to_list()

    values_list = await CustomFieldValue.find(
        CustomFieldValue.company_id == company_id,
        CustomFieldValue.entity_type == entity_type,
        CustomFieldValue.entity_id == entity_id,
    ).to_list()
    values_map = {str(v.schema_id): v for v in values_list}

    # Merge schemas with their values
    result = []
    for schema in schemas:
        schema_id_str = str(schema.id)
        val = values_map.get(schema_id_str)
        result.append({
            "schema_id": schema_id_str,
            "field_name": schema.field_name,
            "display_name": schema.display_name,
            "field_type": schema.field_type,
            "options": schema.options or [],
            "required": schema.required,
            "value": val.value_text if val and val.value_text else (val.value_json if val else None),
        })
    return result


@router.put("/values/{entity_type}/{entity_id}")
async def set_values(
    entity_type: str,
    entity_id: str,
    values: dict,   # {field_name: value}
    current_user: dict = Depends(get_current_user),
):
    """Set custom field values. Pass a dict of {field_name: value}."""
    company_id = current_user["company_id"]
    
    schemas = await CustomFieldSchema.find(
        CustomFieldSchema.company_id == company_id,
        CustomFieldSchema.entity_type == entity_type,
        CustomFieldSchema.is_active == True,
    ).to_list()
    schemas_map = {s.field_name: s for s in schemas}

    updated = 0
    for field_name, raw_value in values.items():
        schema = schemas_map.get(field_name)
        if not schema:
            continue

        # Find existing value or create new
        val_obj = await CustomFieldValue.find_one(
            CustomFieldValue.schema_id == schema.id,
            CustomFieldValue.entity_id == entity_id,
            CustomFieldValue.company_id == company_id,
        )

        # Determine storage column
        is_json = schema.field_type in ("boolean", "multiselect", "number")
        text_val = None if is_json else str(raw_value) if raw_value is not None else None
        json_val = raw_value if is_json else None

        if val_obj:
            val_obj.value_text = text_val
            val_obj.value_json = json_val
            val_obj.updated_at = datetime.utcnow()
            await val_obj.save()
        else:
            val_obj = CustomFieldValue(
                company_id=company_id,
                schema_id=schema.id,
                entity_type=entity_type,
                entity_id=entity_id,
                value_text=text_val,
                value_json=json_val,
            )
            await val_obj.insert()
        updated += 1

    return {"updated": updated, "entity_id": entity_id}


def _ser_schema(s: CustomFieldSchema) -> dict:
    return {
        "id": str(s.id), "entity_type": s.entity_type,
        "field_name": s.field_name, "display_name": s.display_name,
        "field_type": s.field_type, "options": s.options or [],
        "required": s.required, "description": s.description,
        "sort_order": s.sort_order, "is_active": s.is_active,
    }
