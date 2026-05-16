"""HR reviewer CLI — approve, edit, or reject pending draft replies."""
import sys
from pathlib import Path

from app.delivery.draft_store import DraftStore, Draft
from app.delivery.dispatcher import send_approved_draft
from app.email_ingestion.mock_inbox import MockInbox

DB_PATH = "./muster.db"


def show_draft(draft: Draft, index: int, total: int) -> None:
    print(f"\n{'═' * 60}")
    print(f"Draft {index}/{total}  [ID: {draft.id}]")
    print(f"From:    {draft.sender}")
    print(f"Subject: {draft.subject}")
    print(f"{'─' * 60}")
    print(f"EMPLOYEE QUESTION:\n{draft.question}")
    print(f"\nPROPOSED REPLY:\n{draft.proposed_answer}")
    if draft.sources:
        print(f"\nSources: {', '.join(draft.sources)}")
    v = draft.validation
    confidence = int(v.get("confidence", 0) * 100)
    print(f"Validation: {'PASS' if v.get('valid') else 'FAIL'} ({confidence}% confidence)")
    print(f"{'═' * 60}")


def prompt_action() -> str:
    while True:
        choice = input("\n[A]pprove  [E]dit  [R]eject  [S]kip: ").strip().lower()
        if choice in ("a", "e", "r", "s"):
            return choice
        print("Invalid choice. Enter A, E, R, or S.")


def read_multiline(prompt: str) -> str:
    print(prompt + " (press Enter twice when done):")
    lines = []
    while True:
        line = input()
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def main() -> None:
    draft_store = DraftStore(db_path=DB_PATH)
    inbox = MockInbox(db_path=DB_PATH)

    pending = draft_store.get_pending()
    if not pending:
        print("No pending drafts to review.")
        return

    print(f"Muster HR Review Console — {len(pending)} draft(s) pending\n")

    for i, draft in enumerate(pending, 1):
        show_draft(draft, i, len(pending))

        try:
            action = prompt_action()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting review session.")
            break

        if action == "a":
            send_approved_draft(draft.id, draft_store, inbox)
            print("✓ Approved and sent.")

        elif action == "e":
            edited = read_multiline("\nEnter your edited reply")
            if edited:
                send_approved_draft(draft.id, draft_store, inbox, edited_answer=edited)
                print("✓ Edited and sent.")
            else:
                print("Empty reply — skipping.")

        elif action == "r":
            try:
                note = input("Rejection note (optional): ").strip()
            except (KeyboardInterrupt, EOFError):
                note = ""
            draft_store.reject(draft.id, note=note)
            print("✗ Rejected.")

        else:
            print("Skipped.")

    print("\nDone.")


if __name__ == "__main__":
    main()
