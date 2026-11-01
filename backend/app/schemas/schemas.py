from pydantic import BaseModel, EmailStr, Field, AliasChoices, ConfigDict, field_validator
from typing import Optional, List, Any
from datetime import date, datetime
from decimal import Decimal

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = ""
    currency: str = "INR"
    preferred_currency: str = "INR"

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class RefreshIn(BaseModel):
    refresh_token: str

class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    email: str

class UserOut(BaseModel):
    id: int
    email: str
    full_name: str = ""
    currency: str = "INR"
    preferred_currency: str = "INR"
    class Config:
        from_attributes = True

TRANSACTION_TYPES = {"income", "expense", "transfer", "refund"}

class TransactionIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    type: str
    # Amounts are always positive; direction is carried by `type`
    # (a refund is a positive amount with type="refund"). Zero/negative
    # amounts corrupt analytics, so reject them at the boundary.
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = "INR"

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        t = str(v).strip().lower()
        if t not in TRANSACTION_TYPES:
            raise ValueError(f"type must be one of {sorted(TRANSACTION_TYPES)}")
        return t
    category_name: str = Field(default="Uncategorized", validation_alias=AliasChoices("category_name", "category"))
    category_id: Optional[int] = None
    account_id: Optional[int] = None
    merchant: str = ""
    description: str = ""
    notes: str = ""
    date: date
    is_recurring: bool = False

class TransactionOut(TransactionIn):
    id: int
    user_id: int
    class Config:
        from_attributes = True

class CategoryIn(BaseModel):
    name: str
    type: str = "expense"
    icon: str = ""

class BudgetIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    category_name: str = Field(default="Overall", validation_alias=AliasChoices("category_name", "category"))
    amount: Decimal = Field(gt=Decimal("0"), validation_alias=AliasChoices("amount", "limit_amount"))
    month: int = Field(default_factory=lambda: datetime.utcnow().month)
    year: int = Field(default_factory=lambda: datetime.utcnow().year)
    period: Optional[str] = None

class BudgetOut(BudgetIn):
    id: int
    user_id: int
    spent: Optional[float] = None
    remaining: Optional[float] = None
    utilisation: Optional[float] = None
    utilization: Optional[float] = None
    alert_level: Optional[str] = None
    class Config:
        from_attributes = True

class CategorizeIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    description: str = Field(default="", validation_alias=AliasChoices("description", "text"))
    merchant: str = ""

class ChatIn(BaseModel):
    message: str
    conversation_id: Optional[int] = None

class SimulatorIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    category_name: str = Field(validation_alias=AliasChoices("category_name", "category"))
    reduction_percent: float = Field(ge=0, le=100, validation_alias=AliasChoices("reduction_percent", "percentage", "reduction"))
    months: int = 1

class SimulatorCompareIn(BaseModel):
    scenarios: List[SimulatorIn]

class GoalIn(BaseModel):
    name: str
    target_amount: Decimal = Field(gt=Decimal("0"))
    current_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    deadline: Optional[date] = None

class RecurringIn(BaseModel):
    category_name: str = "Uncategorized"
    type: str = "expense"
    amount: Decimal = Field(gt=Decimal("0"))
    merchant: str = ""
    description: str = ""
    frequency: str = "monthly"
    next_date: Optional[date] = None

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        t = str(v).strip().lower()
        if t not in TRANSACTION_TYPES:
            raise ValueError(f"type must be one of {sorted(TRANSACTION_TYPES)}")
        return t

class AffordIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    item_name: str = Field(default="Purchase", validation_alias=AliasChoices("item_name", "item", "name"))
    cost: Decimal = Field(gt=Decimal("0"), validation_alias=AliasChoices("cost", "price", "amount"))
    months: int = Field(default=6, ge=1, le=120)


class SubscriptionOverrideIn(BaseModel):
    merchant: str
    status: str  # confirmed | dismissed
    custom_amount: Optional[float] = None
    custom_frequency: Optional[str] = None
    custom_next_date: Optional[date] = None

class ReminderIn(BaseModel):
    title: str
    amount: Optional[float] = None
    due_date: date
    recurrence: str = "none"  # none | weekly | monthly | yearly
    category_name: Optional[str] = ""
    notes: Optional[str] = ""


class TrajectoryIn(BaseModel):
    category_name: Optional[str] = None
    reduction_percent: float = Field(default=0, ge=0, le=100)
    extra_monthly_savings: float = Field(default=0, ge=0)
    income_change_percent: float = Field(default=0, ge=-100, le=500)
    one_off_expense: float = Field(default=0, ge=0)
    months: int = Field(default=12, ge=1, le=36)
