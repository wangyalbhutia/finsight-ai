"""Structured, READ-ONLY tools for agents. Validated with Pydantic.
Financial WRITE operations are disabled entirely: there are no create/update/delete
transaction tools here, by design."""
from pydantic import BaseModel, Field
from typing import List, Optional

READ_ONLY_TOOLS = ["analytics_summary", "category_breakdown", "forecast", "anomalies", "budget_status", "simulator"]

class ToolInput(BaseModel):
    user_id: int = Field(gt=0)
    message: Optional[str] = ""

class AnalyticsOutput(BaseModel):
    total_income: float
    total_expense: float
    net_balance: float
    savings_rate: float

class ForecastOutput(BaseModel):
    predicted_amount: Optional[float] = None
    insufficient_data: bool = False
    model_version: str

class ChatOutput(BaseModel):
    response: str
    agent: str
    conversation_id: int
    tools_used: List[str] = []
    read_only: bool = True
