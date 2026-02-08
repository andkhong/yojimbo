from app.models.appointment import Appointment, TimeSlot
from app.models.call import Call, CallEvent, ConversationTurn
from app.models.contact import Contact
from app.models.department import Department, StaffMember
from app.models.message import SMSMessage
from app.models.user import DashboardUser

__all__ = [
    "Appointment",
    "Call",
    "CallEvent",
    "Contact",
    "ConversationTurn",
    "DashboardUser",
    "Department",
    "SMSMessage",
    "StaffMember",
    "TimeSlot",
]
