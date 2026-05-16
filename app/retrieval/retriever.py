from app.indexer.store import PolicyStore


def retrieve(question: str, store: PolicyStore, n_results: int = 5) -> list[dict]:
    return store.query(question, n_results=n_results)
