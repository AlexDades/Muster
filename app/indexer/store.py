import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


class PolicyStore:
    def __init__(self, db_path: str, collection_name: str):
        self._client = chromadb.PersistentClient(path=db_path)
        ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    def add_document(self, doc_id: str, chunks: list[str], filename: str) -> None:
        if not chunks:
            return
        ids = [f"{doc_id}__chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {"doc_id": doc_id, "filename": filename, "chunk_index": i}
            for i in range(len(chunks))
        ]
        self._collection.add(documents=chunks, ids=ids, metadatas=metadatas)

    def update_document(self, doc_id: str, chunks: list[str], filename: str) -> None:
        self.delete_document(doc_id)
        self.add_document(doc_id, chunks, filename)

    def delete_document(self, doc_id: str) -> None:
        existing = self._collection.get(where={"doc_id": doc_id})
        if existing["ids"]:
            self._collection.delete(ids=existing["ids"])

    def query(self, text: str, n_results: int = 5) -> list[dict]:
        count = self._collection.count()
        if count == 0:
            return []
        results = self._collection.query(
            query_texts=[text],
            n_results=min(n_results, count),
        )
        hits = []
        for i, doc in enumerate(results["documents"][0]):
            hits.append({
                "text": doc,
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
        return hits

    def list_documents(self) -> list[dict]:
        results = self._collection.get()
        seen: set[str] = set()
        docs = []
        for meta in results["metadatas"]:
            doc_id = meta["doc_id"]
            if doc_id not in seen:
                seen.add(doc_id)
                docs.append({"doc_id": doc_id, "filename": meta["filename"]})
        return docs

    def count(self) -> int:
        return self._collection.count()
