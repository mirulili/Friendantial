import logging
from typing import List

import chromadb
from chromadb.utils import embedding_functions


class SimpleRAG:
    def __init__(self):
        # 로컬 메모리에 저장되는 가벼운 ChromaDB 클라이언트 생성
        self.client = chromadb.Client()
        self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="jhgan/ko-sroberta-multitask"
        )

    def create_collection(self, stock_code: str, documents: List[str]):
        """특정 종목을 위한 컬렉션을 생성하고 문서를 저장합니다."""
        # ChromaDB 컬렉션 이름 규칙 준수 (점 . 을 언더바 _ 로 변경)
        # 예: "######.KS" -> "stock_######_KS"
        safe_name = f"stock_{stock_code.replace('.', '_')}"

        # 기존 컬렉션 삭제 시 에러 방지 (모든 예외 처리)
        try:
            self.client.delete_collection(name=safe_name)
        except Exception:
            pass

        collection = self.client.create_collection(
            name=safe_name, embedding_function=self.ef
        )

        # 문서에 ID 부여하여 저장
        if documents:
            ids = [f"id_{i}" for i in range(len(documents))]
            collection.add(documents=documents, ids=ids)
        return collection

    def query(self, stock_code: str, question: str, n_results: int = 5) -> List[str]:
        """질문과 가장 유사한 문서를 검색합니다."""
        # 저장할 때와 동일한 이름 규칙 적용
        safe_name = f"stock_{stock_code.replace('.', '_')}"

        try:
            collection = self.client.get_collection(
                name=safe_name, embedding_function=self.ef
            )
            results = collection.query(
                query_texts=[question],
                n_results=min(
                    n_results, collection.count()
                ),  # 문서 수보다 많이 요청하면 에러 방지
            )
            # results['documents']는 [[doc1, doc2, ...]] 형태이므로 첫 번째 리스트 반환
            return results["documents"][0] if results["documents"] else []
        except Exception as e:
            logging.warning(f"RAG 검색 실패 ({safe_name}): {e}")
            return []


# 싱글톤 인스턴스
rag_engine = SimpleRAG()
