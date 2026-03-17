from typing import Any
from decimal import Decimal

try:
    from bson.decimal128 import Decimal128
except ImportError:
    Decimal128 = None

def to_float(val: Any) -> float:
    """Safely convert a value to float, handling Decimal128, Decimal, and strings."""
    if val is None:
        return 0.0
    
    if Decimal128 and isinstance(val, Decimal128):
        return float(val.to_decimal())
    
    if isinstance(val, Decimal):
        return float(val)
        
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0
