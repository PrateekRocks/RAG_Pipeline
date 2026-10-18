import hashlib
import json
import uuid
import tiktoken
from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.services.chunking import chunk_recursive
from app.services.embeddings import embed_texts

enc = tiktoken.get_encoding("cl100k_base")

async def ingest_document(
    tenant_id: str,
    source_uri: str,
    title: str,
    raw_text: str,
    metadata: dict | None = None
) -> str:
    metadata = metadata or {}
    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # 1. Insert or retrieve document
            doc_res = await session.execute(
                text("""
                    INSERT INTO documents (tenant_id, source_uri, title, content_hash, metadata)
                    VALUES (:tenant_id, :source_uri, :title, :content_hash, :metadata)
                    ON CONFLICT (tenant_id, content_hash) 
                    DO UPDATE SET title = EXCLUDED.title, metadata = EXCLUDED.metadata, updated_at = now()
                    RETURNING id
                """),
                {
                    "tenant_id": tenant_id,
                    "source_uri": source_uri,
                    "title": title,
                    "content_hash": content_hash,
                    "metadata": json.dumps(metadata)
                }
            )
            document_id = str(doc_res.scalar_one())

            # Delete any prior chunks for this document in case of re-ingestion
            await session.execute(
                text("DELETE FROM chunks WHERE document_id = :doc_id"),
                {"doc_id": document_id}
            )

            # 2. Chunk the text
            chunks = chunk_recursive(raw_text)
            if not chunks:
                return document_id

            # 3. Generate embeddings for all chunks in batch
            embeddings = await embed_texts(chunks)

            # 4. Insert chunks into the database
            for idx, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                token_count = len(enc.encode(chunk_text))
                await session.execute(
                    text("""
                        INSERT INTO chunks (
                            id, document_id, tenant_id, chunk_index, content, token_count, embedding, metadata
                        ) VALUES (
                            :id, :document_id, :tenant_id, :chunk_index, :content, :token_count, CAST(:embedding AS vector), :metadata
                        )
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "document_id": document_id,
                        "tenant_id": tenant_id,
                        "chunk_index": idx,
                        "content": chunk_text,
                        "token_count": token_count,
                        "embedding": str(embedding),
                        "metadata": json.dumps({"source": source_uri, "index": idx})
                    }
                )

        return document_id
