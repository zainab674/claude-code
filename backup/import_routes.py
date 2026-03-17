"""
Bulk employee import via CSV upload.
POST /import/employees   multipart CSV file → creates employees in bulk

Expected CSV columns (required: first_name, last_name, hire_date, pay_type, pay_rate):
first_name, last_name, email, phone, hire_date, pay_type, pay_rate, pay_frequency,
department, job_title, filing_status, state_code,
health_insurance_deduction, dental_deduction, vision_deduction,
retirement_401k_pct, hsa_deduction
"""
import csv
import io
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import Employee
from utils.auth import get_current_user

router = APIRouter(prefix="/import", tags=["import"])

REQUIRED_COLS = {"first_name", "last_name", "hire_date", "pay_type", "pay_rate"}

FLOAT_COLS = {
    "pay_rate", "health_insurance_deduction", "dental_deduction",
    "vision_deduction", "retirement_401k_pct", "hsa_deduction",
    "garnishment_amount", "additional_federal_withholding",
}
INT_COLS = {"federal_allowances"}
BOOL_COLS = {"exempt_from_federal", "exempt_from_state"}

VALID_PAY_TYPES = {"salary", "hourly", "contract"}
VALID_FREQUENCIES = {"weekly", "biweekly", "semimonthly", "monthly"}
VALID_FILING = {"single", "married", "head_of_household"}


def _parse_date(s: str) -> date:
    """Accept YYYY-MM-DD, MM/DD/YYYY, M/D/YYYY."""
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s}")


def _parse_bool(s: str) -> bool:
    return s.strip().lower() in ("1", "true", "yes", "y")


@router.post("/employees")
async def import_employees(
    file: UploadFile = File(...),
    dry_run: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a CSV file to bulk-import employees.
    Set ?dry_run=true to validate without saving.
    Returns a summary with per-row errors.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")   # handles Excel BOM
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "Empty or unreadable CSV")

    # Normalize column names
    headers = {h.strip().lower().replace(" ", "_") for h in reader.fieldnames}
    missing = REQUIRED_COLS - headers
    if missing:
        raise HTTPException(400, f"Missing required columns: {', '.join(sorted(missing))}")

    created = []
    errors = []

    for i, raw_row in enumerate(reader, start=2):   # row 1 = headers
        row = {k.strip().lower().replace(" ", "_"): (v or "").strip()
               for k, v in raw_row.items() if k}
        row_errors = []

        # Required fields
        for col in REQUIRED_COLS:
            if not row.get(col):
                row_errors.append(f"{col} is required")

        if row_errors:
            errors.append({"row": i, "errors": row_errors})
            continue

        # Parse and validate
        try:
            hire_date = _parse_date(row["hire_date"])
        except ValueError as e:
            errors.append({"row": i, "errors": [str(e)]})
            continue

        pay_type = row["pay_type"].lower()
        if pay_type not in VALID_PAY_TYPES:
            errors.append({"row": i, "errors": [f"pay_type must be one of {VALID_PAY_TYPES}"]})
            continue

        try:
            pay_rate = float(row["pay_rate"].replace(",", "").replace("$", ""))
        except ValueError:
            errors.append({"row": i, "errors": [f"pay_rate must be numeric, got: {row['pay_rate']}"]})
            continue

        if pay_rate <= 0:
            errors.append({"row": i, "errors": ["pay_rate must be > 0"]})
            continue

        pay_freq = row.get("pay_frequency", "biweekly").lower()
        if pay_freq not in VALID_FREQUENCIES:
            pay_freq = "biweekly"

        filing = row.get("filing_status", "single").lower()
        if filing not in VALID_FILING:
            filing = "single"

        def safe_float(col, default=0.0):
            v = row.get(col, "").replace(",", "").replace("$", "")
            try:
                return float(v) if v else default
            except ValueError:
                return default

        emp_data = {
            "company_id": current_user["company_id"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "email": row.get("email") or None,
            "phone": row.get("phone") or None,
            "hire_date": hire_date,
            "pay_type": pay_type,
            "pay_rate": pay_rate,
            "pay_frequency": pay_freq,
            "department": row.get("department") or None,
            "job_title": row.get("job_title") or None,
            "filing_status": filing,
            "state_code": (row.get("state_code") or "NY").upper()[:2],
            "federal_allowances": int(safe_float("federal_allowances", 0)),
            "additional_federal_withholding": safe_float("additional_federal_withholding"),
            "health_insurance_deduction": safe_float("health_insurance_deduction"),
            "dental_deduction": safe_float("dental_deduction"),
            "vision_deduction": safe_float("vision_deduction"),
            "retirement_401k_pct": safe_float("retirement_401k_pct"),
            "hsa_deduction": safe_float("hsa_deduction"),
            "garnishment_amount": safe_float("garnishment_amount"),
            "exempt_from_federal": _parse_bool(row.get("exempt_from_federal", "false")),
            "exempt_from_state": _parse_bool(row.get("exempt_from_state", "false")),
            "address_line1": row.get("address_line1") or None,
            "city": row.get("city") or None,
            "state": row.get("state") or None,
            "zip": row.get("zip") or None,
        }

        if not dry_run:
            emp = Employee(**emp_data)
            db.add(emp)
            created.append({"row": i, "name": f"{emp_data['first_name']} {emp_data['last_name']}"})
        else:
            created.append({"row": i, "name": f"{emp_data['first_name']} {emp_data['last_name']}", "preview": emp_data})

    if not dry_run and created:
        await db.commit()

    return {
        "dry_run": dry_run,
        "rows_processed": len(created) + len(errors),
        "created": len(created) if not dry_run else 0,
        "valid": len(created) if dry_run else 0,
        "errors": len(errors),
        "details": created[:50],      # return first 50 to avoid huge response
        "error_details": errors[:50],
    }


@router.get("/employees/template")
async def download_import_template():
    """Download a CSV template for bulk employee import."""
    import io
    from fastapi import Response
    cols = [
        "first_name", "last_name", "email", "phone", "hire_date",
        "pay_type", "pay_rate", "pay_frequency", "department", "job_title",
        "filing_status", "state_code", "federal_allowances",
        "additional_federal_withholding",
        "health_insurance_deduction", "dental_deduction", "vision_deduction",
        "retirement_401k_pct", "hsa_deduction", "garnishment_amount",
        "address_line1", "city", "state", "zip",
    ]
    example = {
        "first_name": "Jane", "last_name": "Smith", "email": "jane@example.com",
        "phone": "555-1234", "hire_date": "2026-01-15", "pay_type": "salary",
        "pay_rate": "75000", "pay_frequency": "biweekly", "department": "Engineering",
        "job_title": "Engineer", "filing_status": "single", "state_code": "NY",
        "federal_allowances": "0", "additional_federal_withholding": "0",
        "health_insurance_deduction": "300", "dental_deduction": "25",
        "vision_deduction": "10", "retirement_401k_pct": "0.05",
        "hsa_deduction": "0", "garnishment_amount": "0",
        "address_line1": "123 Main St", "city": "New York", "state": "NY", "zip": "10001",
    }
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    writer.writerow(example)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="employee-import-template.csv"'},
    )
