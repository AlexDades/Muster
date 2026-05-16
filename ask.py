"""Interactive Q&A against the indexed HR policy documents."""
import sys
from pathlib import Path
from app.config import settings
from app.indexer.store import PolicyStore
from app.indexer.pipeline import index_document
from app.retrieval.pipeline import answer_question
import anthropic

SAMPLE_DOCS_DIR = Path(__file__).parent / "sample_docs"
DB_PATH = "./chroma_db"
COLLECTION = "hr_policies"


def build_or_load_store() -> PolicyStore:
    store = PolicyStore(db_path=DB_PATH, collection_name=COLLECTION)
    if store.count() == 0:
        print("Indexing policy documents for the first time...")
        docs = sorted(SAMPLE_DOCS_DIR.glob("*.pdf")) + sorted(SAMPLE_DOCS_DIR.glob("*.docx"))
        for doc in docs:
            result = index_document(doc, store=store)
            print(f"  ✓ {result['filename']} ({result['chunks']} chunks)")
        print(f"\nIndexed {len(docs)} documents ({store.count()} total chunks)\n")
    else:
        print(f"Loaded existing index ({store.count()} chunks across all documents)\n")
    return store


def print_result(result: dict) -> None:
    print("\n" + "─" * 60)
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
    print("─" * 60 + "\n")


def main() -> None:
    if not settings.anthropic_api_key:
        print("Error: ANTHROPIC_API_KEY is not set in your .env file.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    store = build_or_load_store()

    print("Ask any question about the company's HR policies.")
    print("Type 'quit' or press Ctrl+C to exit.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        print("Thinking...")
        result = answer_question(question, store, n_results=5, client=client)
        print_result(result)


if __name__ == "__main__":
    main()
