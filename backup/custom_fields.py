"""
Custom fields — add arbitrary metadata to employees, jobs, or pay runs.
Admins define field schemas; users fill in values.

POST /custom-fields/schema           define a new field
GET  /custom-fields/schema           list field definitions
GET  /custom-fields/schema/{entity}  list fields for entity type
PUT  /custom-fields/values/{entity}/{id}  set field values for a record
GET  /custom-fields/values/{entity}/{id}  get field values for a record

Supported entity types: employee, job, pay_run, contractor
Field types: text, number, date, boolean, select, multiselect
"""
import uuid
from datetime import datetime
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, select
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/custom-fields", tags=["custom-fields"])

ENTITY_TYPES = ["employee", "job", "pay_run", "contractor", "candidate"]
FIELD_TYPES = ["text", "number", "date", "boolean", "select", "multiselect", "url", "email"]


class CustomFieldSchema(Base):
    __tablename__ = "custom_field_schemas"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    entity_type = Column(String(30), nullable=False)   # employee|job|pay_run|contractor
    field_name = Column(String(100), nullable=False)   # internal key (snake_case)
    display_name = Column(String(200), nullable=False) # shown in UI
    field_type = Column(String(30), nullable=False)
    options = Column(JSONB, default=list)              # for select/multiselect
    required = Column(Boolean, default=False)
    description = Column(Text)
    sort_order = Column(String(5), default="0")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class CustomFieldValue(Base):
    __tablename__ = "custom_field_values"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    schema_id = Column(UUID(as_uuid=True), ForeignKey("custom_field_schemas.id", ondelete="CASCADE"))
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(String(100), nullable=False)   # UUID of the entity
    value_text = Column(Text)
    value_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class FieldSchemaCreate(BaseModel):
    entity_type: str
    field_name: str
    display_name: str
    field_type: str
    options: list = []
    required: bool = False
    description: Optional[str] = None
    sort_order: int = 0


@router.get("/schema")
async def list_schemas(
    entity_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(CustomFieldSchema).where(
        CustomFieldSchema.company_id == current_user["company_id"],
        CustomFieldSchema.is_active == True,
    )
    if entity_type:
        q = q.where(CustomFieldSchema.entity_type == entity_type)
    q = q.order_by(CustomFieldSchema.entity_type, CustomFieldSchema.sort_order)
    result = await db.execute(q)
    return [_ser_schema(s) for s in result.scalars().all()]


@router.post("/schema", status_code=201)
async def create_schema(
    body: FieldSchemaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if body.entity_type not in ENTITY_TYPES:
        raise HTTPException(400, f"entity_type must be: {', '.join(ENTITY_TYPES)}")
    if body.field_type not in FIELD_TYPES:
        raise HTTPException(400, f"field_type must be: {', '.join(FIELD_TYPES)}")

    # Validate field_name is snake_case
    if not all(c.isalnum() or c == '_' for c in body.field_name):
        raise HTTPException(400, "field_name must contain only letters, numbers, and underscores")

    # Check for duplicate
    existing = await db.execute(
        select(CustomFieldSchema).where(
            CustomFieldSchema.company_id == current_user["company_id"],
            CustomFieldSchema.entity_type == body.entity_type,
            CustomFieldSchema.field_name == body.field_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Field '{body.field_name}' already exists for {body.entity_type}")

    schema = CustomFieldSchema(
        company_id=current_user["company_id"],
        sort_order=str(body.sort_order),
        **{k: v for k, v in body.model_dump().items() if k != 'sort_order'},
    )
    db.add(schema)
    await db.commit()
    await db.refresh(schema)
    return _ser_schema(schema)


@router.delete("/schema/{schema_id}", status_code=204)
async def delete_schema(
    schema_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(CustomFieldSchema).where(
            CustomFieldSchema.id == schema_id,
            CustomFieldSchema.company_id == current_user["company_id"],
        )
    )
    schema = result.scalar_one_or_none()
    if not schema:
        raise HTTPException(404, "Field schema not found")
    schema.is_active = False
    await db.commit()


@router.get("/values/{entity_type}/{entity_id}")
async def get_values(
    entity_type: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get all custom field values for a specific entity."""
    schemas_res = await db.execute(
        select(CustomFieldSchema).where(
            CustomFieldSchema.company_id == current_user["company_id"],
            CustomFieldSchema.entity_type == entity_type,
            CustomFieldSchema.is_active == True,
        ).order_by(CustomFieldSchema.sort_order)
    )
    schemas = {str(s.id): s for s in schemas_res.scalars().all()}

    values_res = await db.execute(
        select(CustomFieldValue).where(
            CustomFieldValue.company_id == current_user["company_id"],
            CustomFieldValue.entity_type == entity_type,
            CustomFieldValue.entity_id == entity_id,
        )
    )
    values = {str(v.schema_id): v for v in values_res.scalars().all()}

    # Merge schemas with their values
    result = []
    for schema_id, schema in schemas.items():
        val = values.get(schema_id)
        result.append({
            "schema_id": schema_id,
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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Set custom field values. Pass a dict of {field_name: value}."""
    # Load schemas indexed by field_name
    schemas_res = await db.execute(
        select(CustomFieldSchema).where(
            CustomFieldSchema.company_id == current_user["company_id"],
            CustomFieldSchema.entity_type == entity_type,
            CustomFieldSchema.is_active == True,
        )
    )
    schemas = {s.field_name: s for s in schemas_res.scalars().all()}

    updated = 0
    for field_name, raw_value in values.items():
        schema = schemas.get(field_name)
        if not schema:
            continue

        # Find existing value or create new
        existing_res = await db.execute(
            select(CustomFieldValue).where(
                CustomFieldValue.schema_id == schema.id,
                CustomFieldValue.entity_id == entity_id,
                CustomFieldValue.company_id == current_user["company_id"],
            )
        )
        val_obj = existing_res.scalar_one_or_none()

        # Determine storage column
        is_json = schema.field_type in ("boolean", "multiselect", "number")
        text_val = None if is_json else str(raw_value) if raw_value is not None else None
        json_val = raw_value if is_json else None

        if val_obj:
            val_obj.value_text = text_val
            val_obj.value_json = json_val
            val_obj.updated_at = datetime.utcnow()
        else:
            val_obj = CustomFieldValue(
                company_id=current_user["company_id"],
                schema_id=schema.id,
                entity_type=entity_type,
                entity_id=entity_id,
                value_text=text_val,
                value_json=json_val,
            )
            db.add(val_obj)
        updated += 1

    await db.commit()
    return {"updated": updated, "entity_id": entity_id}


def _ser_schema(s: CustomFieldSchema) -> dict:
    return {
        "id": str(s.id), "entity_type": s.entity_type,
        "field_name": s.field_name, "display_name": s.display_name,
        "field_type": s.field_type, "options": s.options or [],
        "required": s.required, "description": s.description,
        "sort_order": s.sort_order, "is_active": s.is_active,
    }
