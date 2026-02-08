"""Seed the database with sample departments, time slots, staff, and a demo admin user."""

import asyncio
import sys
from datetime import time
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.security import hash_password
from app.database import async_session_factory, init_db
from app.models.appointment import TimeSlot
from app.models.department import Department, StaffMember
from app.models.user import DashboardUser

DEPARTMENTS = [
    {
        "name": "General Information",
        "code": "GENERAL",
        "description": "General inquiries, directions, and basic city information",
        "operating_hours": '{"mon-fri": "8:00-17:00"}',
        "phone_extension": "100",
    },
    {
        "name": "Building Permits",
        "code": "BLDG_PERMITS",
        "description": "Building permits, zoning approvals, and construction inspections",
        "operating_hours": '{"mon-fri": "9:00-16:00"}',
        "phone_extension": "200",
    },
    {
        "name": "Business Licenses",
        "code": "BIZ_LICENSE",
        "description": "Business license applications, renewals, and compliance",
        "operating_hours": '{"mon-fri": "9:00-16:00"}',
        "phone_extension": "210",
    },
    {
        "name": "Public Works",
        "code": "PUBLIC_WORKS",
        "description": "Road maintenance, water, sewer, and infrastructure issues",
        "operating_hours": '{"mon-fri": "7:00-16:00"}',
        "phone_extension": "300",
    },
    {
        "name": "Parks & Recreation",
        "code": "PARKS_REC",
        "description": "Park reservations, recreational programs, and facility rentals",
        "operating_hours": '{"mon-sat": "8:00-18:00"}',
        "phone_extension": "400",
    },
    {
        "name": "Finance & Tax",
        "code": "FINANCE",
        "description": "Property tax payments, utility billing, and financial inquiries",
        "operating_hours": '{"mon-fri": "8:30-16:30"}',
        "phone_extension": "500",
    },
    {
        "name": "Code Enforcement",
        "code": "CODE_ENFORCE",
        "description": "Property code violations, complaints, and compliance inspections",
        "operating_hours": '{"mon-fri": "8:00-17:00"}',
        "phone_extension": "600",
    },
]

STAFF_MEMBERS = [
    ("General Information", "Maria Santos", "Receptionist", "msantos@city.gov"),
    ("General Information", "James Chen", "Information Specialist", "jchen@city.gov"),
    ("Building Permits", "Robert Johnson", "Permit Specialist", "rjohnson@city.gov"),
    ("Building Permits", "Sarah Kim", "Plans Examiner", "skim@city.gov"),
    ("Business Licenses", "Linda Nguyen", "License Coordinator", "lnguyen@city.gov"),
    ("Public Works", "Michael Brown", "Operations Manager", "mbrown@city.gov"),
    ("Parks & Recreation", "Emily Davis", "Program Coordinator", "edavis@city.gov"),
    ("Finance & Tax", "David Wilson", "Tax Analyst", "dwilson@city.gov"),
    ("Code Enforcement", "Patricia Martinez", "Code Officer", "pmartinez@city.gov"),
]


async def seed():
    await init_db()

    async with async_session_factory() as db:
        # Check if already seeded
        from sqlalchemy import select, func

        count = (await db.execute(
            select(func.count()).select_from(Department)
        )).scalar()
        if count and count > 0:
            print(f"Database already has {count} departments. Skipping seed.")
            return

        # Departments
        dept_map = {}
        for dept_data in DEPARTMENTS:
            dept = Department(**dept_data)
            db.add(dept)
            await db.flush()
            dept_map[dept.name] = dept
            print(f"  Created department: {dept.name} (ID: {dept.id})")

        # Time slots: Mon-Fri 9am-4pm, 30-min slots for all departments
        for dept in dept_map.values():
            for day in range(5):  # Monday=0 through Friday=4
                slot = TimeSlot(
                    department_id=dept.id,
                    day_of_week=day,
                    start_time=time(9, 0),
                    end_time=time(16, 0),
                    slot_duration_minutes=30,
                    max_concurrent=2,
                )
                db.add(slot)

        # Staff members
        for dept_name, name, role, email in STAFF_MEMBERS:
            if dept_name in dept_map:
                staff = StaffMember(
                    department_id=dept_map[dept_name].id,
                    name=name,
                    role=role,
                    email=email,
                )
                db.add(staff)
                print(f"  Created staff: {name} ({dept_name})")

        # Demo admin user
        admin = DashboardUser(
            username="admin",
            password_hash=hash_password("admin"),
            name="System Administrator",
            role="admin",
        )
        db.add(admin)
        print("  Created admin user: admin/admin")

        # Demo staff user
        staff_user = DashboardUser(
            username="staff",
            password_hash=hash_password("staff"),
            name="Front Desk Staff",
            department_id=dept_map["General Information"].id,
            role="staff",
        )
        db.add(staff_user)
        print("  Created staff user: staff/staff")

        await db.commit()
        print("\nSeed completed successfully!")


if __name__ == "__main__":
    print("Seeding Yojimbo database...\n")
    asyncio.run(seed())
