"""Seeds the mock inbox with realistic HR question emails."""
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.email_ingestion.mock_inbox import MockInbox
from app.email_ingestion.models import Email

DB_PATH = str(Path(__file__).parent.parent / "mock_inbox.db")

EMAILS = [
    (
        "sarah.jones@company.com",
        "Vacation days question",
        "Hi HR,\n\nI just joined last month and wanted to check — how many vacation days am I entitled to per year? Also, can I take them all at once?\n\nThanks,\nSarah",
    ),
    (
        "mark.brown@company.com",
        "Expense reimbursement",
        "Hello,\n\nI have a business lunch receipt for EUR 120 for 3 people. Is this within policy? And how do I submit it?\n\nBest,\nMark",
    ),
    (
        "alice.white@company.com",
        "Remote work days",
        "Hi team,\n\nI'd like to work from home more often. What is the maximum number of days per week I can work remotely?\n\nThanks,\nAlice",
    ),
    (
        "tom.davis@company.com",
        "Parental leave",
        "Hi,\n\nMy wife and I are expecting a baby in 3 months. How much paid parental leave am I entitled to as the secondary caregiver, and when do I need to notify HR?\n\nRegards,\nTom",
    ),
    (
        "emily.clark@company.com",
        "Password policy",
        "Hello HR,\n\nIT asked me to update my password. What are the exact requirements? Length, complexity, etc.?\n\nThanks,\nEmily",
    ),
    (
        "james.martin@company.com",
        "Business travel — flight class",
        "Hi,\n\nI have a 7-hour flight to New York next month for a client meeting. Am I allowed to book business class?\n\nJames",
    ),
    (
        "laura.taylor@company.com",
        "Performance review rating",
        "Hello,\n\nI'm preparing for my annual review. What score do I need to be considered for a promotion?\n\nThanks,\nLaura",
    ),
    (
        "david.wilson@company.com",
        "Health benefits enrollment",
        "Hi,\n\nI started 3 weeks ago and haven't enrolled in health insurance yet. Is it too late? What's the deadline?\n\nDavid",
    ),
    (
        "nina.moore@company.com",
        "Sick leave policy",
        "Hi HR team,\n\nI've been unwell and may need to take several days off. How many sick days do I get and do I need a doctor's note?\n\nNina",
    ),
    (
        "chris.lee@company.com",
        "Re: Expense reimbursement",
        "Hi,\n\nFollowing up on my previous question. I was on a business trip last week and spent EUR 180 on a hotel room per night. Is that reimbursable?\n\nOn Mon, 6 May wrote:\n> Hi Chris, please check the expense policy.\n\nThanks,\nChris",
    ),
]


def seed(db_path: str = DB_PATH) -> None:
    inbox = MockInbox(db_path=db_path)
    base_time = datetime.utcnow() - timedelta(hours=len(EMAILS))

    for i, (sender, subject, body) in enumerate(EMAILS):
        email = Email(
            sender=sender,
            subject=subject,
            body=body,
            message_id=str(uuid.uuid4()),
            received_at=base_time + timedelta(hours=i),
        )
        inbox.add_email(email)

    print(f"Seeded {inbox.count()} emails into {db_path}")


if __name__ == "__main__":
    seed()
