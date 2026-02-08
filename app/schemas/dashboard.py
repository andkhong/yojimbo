from pydantic import BaseModel


class DashboardStats(BaseModel):
    today_calls: int = 0
    active_calls: int = 0
    today_appointments: int = 0
    total_contacts: int = 0
    language_breakdown: dict[str, int] = {}
    avg_call_duration: float = 0.0


class ActivityItem(BaseModel):
    type: str  # call, appointment, sms
    description: str
    timestamp: str
    language: str | None = None
    status: str | None = None
