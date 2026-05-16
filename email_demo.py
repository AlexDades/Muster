"""Simulate sending an HR question by email and receiving a reply."""
import sys
import uuid
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.email_ingestion.mock_inbox import MockInbox
from app.email_ingestion.models import Email
from app.email_ingestion.poller import process_inbox
from app.indexer.store import PolicyStore
from app.indexer.pipeline import index_document
import anthropic

SAMPLE_DOCS_DIR = Path(__file__).parent / "sample_docs"
DB_PATH = "./mock_inbox.db"
CHROMA_PATH = "./chroma_db"
COLLECTION = "hr_policies"


def build_or_load_store() -> PolicyStore:
    store = PolicyStore(db_path=CHROMA_PATH, collection_name=COLLECTION)
    if store.count() == 0:
        print("Indexing policy documents for the first time...")
        docs = sorted(SAMPLE_DOCS_DIR.glob("*.pdf")) + sorted(SAMPLE_DOCS_DIR.glob("*.docx"))
        for doc in docs:
            result = index_document(doc, store=store)
            print(f"  ✓ {result['filename']}")
        print()
    return store


def print_reply(result: dict) -> None:
    print("\n" + "═" * 60)
    print(f"FROM:    hr-assistant@muster.team")
    print(f"TO:      {result['sender']}")
    print(f"SUBJECT: Re: {result['subject']}")
    print("─" * 60)
    print(result["answer"])

    if result["sources"]:
        print("\nSources: " + ", ".join(result["sources"]))

    v = result["validation"]
    status = "PASS" if v["valid"] else "FAIL"
    confidence = int(v["confidence"] * 100)
    print(f"Validation: {status} ({confidence}% confidence)")
    if v["issues"]:
        for issue in v["issues"]:
            print(f"  ! {issue}")
    print("═" * 60 + "\n")


def main() -> None:
    if not settings.anthropic_api_key:
        print("Error: ANTHROPIC_API_KEY is not set in your .env file.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    store = build_or_load_store()
    inbox = MockInbox(db_path=DB_PATH)

    print("Muster HR Email Simulator")
    print("Type your question as if sending an email to HR.")
    print("Type 'quit' or press Ctrl+C to exit.\n")

    while True:
        try:
            sender = input("Your email address: ").strip()
            if sender.lower() in ("quit", "exit", "q"):
                break
            if not sender:
                continue

            subject = input("Subject: ").strip() or "HR Question"
            print("Message (press Enter twice when done):")

            lines = []
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            body = "\n".join(lines).strip()

            if not body:
                print("Message body cannot be empty.\n")
                continue

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        email = Email(
            sender=sender,
            subject=subject,
            body=body,
            message_id=str(uuid.uuid4()),
            received_at=datetime.utcnow(),
        )
        inbox.add_email(email)

        print("\nSending... ", end="", flush=True)
        results = process_inbox(inbox, store, client)
        print("done.")

        for result in results:
            print_reply(result)


if __name__ == "__main__":
    main()
