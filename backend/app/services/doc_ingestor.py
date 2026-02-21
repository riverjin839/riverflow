"""문서 수집 서비스 - PDF/텍스트 파일을 청킹하여 임베딩 후 DB에 저장."""

import logging
from io import BytesIO

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .embedding import EmbeddingService

logger = logging.getLogger(__name__)

# 청크 크기 (문자 수)
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def extract_text_from_pdf(data: bytes) -> str:
    """PDF 바이트에서 텍스트 추출."""
    from PyPDF2 import PdfReader

    reader = PdfReader(BytesIO(data))
    pages = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            pages.append(t.strip())
    return "\n\n".join(pages)


def chunk_text(text_content: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """텍스트를 겹치는 청크로 분할."""
    if not text_content or len(text_content) <= chunk_size:
        return [text_content] if text_content else []

    chunks = []
    start = 0
    while start < len(text_content):
        end = start + chunk_size
        chunk = text_content[start:end]

        # 문장 경계에서 자르기 시도
        if end < len(text_content):
            for sep in ["\n\n", "\n", ". ", "! ", "? ", ", "]:
                last_sep = chunk.rfind(sep)
                if last_sep > chunk_size // 2:
                    chunk = chunk[: last_sep + len(sep)]
                    end = start + len(chunk)
                    break

        chunk = chunk.strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap

    return chunks


async def ingest_document(
    db: AsyncSession,
    title: str,
    content: str,
    doc_type: str,
    embedding_svc: EmbeddingService | None = None,
) -> int:
    """텍스트를 청킹 + 임베딩하여 user_documents에 저장. 저장된 청크 수 반환."""
    chunks = chunk_text(content)
    if not chunks:
        return 0

    own_svc = embedding_svc is None
    if own_svc:
        embedding_svc = EmbeddingService()

    try:
        count = 0
        for i, chunk in enumerate(chunks):
            chunk_title = f"{title} [{i + 1}/{len(chunks)}]" if len(chunks) > 1 else title
            try:
                vec = await embedding_svc.embed(chunk)
                await db.execute(
                    text(
                        "INSERT INTO user_documents (doc_type, title, content, embedding) "
                        "VALUES (:doc_type, :title, :content, :embedding::vector)"
                    ),
                    {
                        "doc_type": doc_type,
                        "title": chunk_title,
                        "content": chunk,
                        "embedding": str(vec),
                    },
                )
                count += 1
            except Exception as e:
                logger.warning("청크 %d 임베딩/저장 실패: %s", i, e)
                # 임베딩 실패 시 벡터 없이 저장
                await db.execute(
                    text(
                        "INSERT INTO user_documents (doc_type, title, content) "
                        "VALUES (:doc_type, :title, :content)"
                    ),
                    {"doc_type": doc_type, "title": chunk_title, "content": chunk},
                )
                count += 1

        await db.commit()
        return count
    finally:
        if own_svc:
            await embedding_svc.close()
