from langchain_text_splitters import RecursiveCharacterTextSplitter
from fastembed import TextEmbedding
from langchain_core.embeddings import Embeddings


class LocalEmbeddings(Embeddings):
    def __init__(self):
        self.model = TextEmbedding(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.embed(texts)
        return [vector.tolist() for vector in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        if not isinstance(text, str):
            raise TypeError("embed_query() harus menerima string, bukan list")

        return self._embed([text])[0]


embeddings = LocalEmbeddings()

# Inisialisasi Text Splitter
splitter = RecursiveCharacterTextSplitter(
    chunk_size=300,
    chunk_overlap=50,
)
