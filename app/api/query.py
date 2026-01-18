# app/api/query.py
"""RAG Query API"""

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
import json
import logging

from app.config import settings
from app.processing.embedder import TextEmbedder
from app.auth.middleware import require_auth, User

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# LLM Provider Abstraction
# =============================================================================

async def generate_with_llm(system_prompt: str, user_message: str) -> str:
    """Generate response using configured LLM provider"""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "gemini":
        return await _generate_gemini(system_prompt, user_message)
    elif provider == "vertex":
        return await _generate_vertex(system_prompt, user_message)
    elif provider == "anthropic":
        return await _generate_anthropic(system_prompt, user_message)
    elif provider == "openai":
        return await _generate_openai(system_prompt, user_message)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


async def _generate_gemini(system_prompt: str, user_message: str) -> str:
    """Generate with Google Gemini"""
    import google.generativeai as genai

    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is required for Gemini provider")

    genai.configure(api_key=settings.GEMINI_API_KEY)

    model = genai.GenerativeModel(
        model_name=settings.LLM_MODEL or "gemini-1.5-flash",
        system_instruction=system_prompt
    )

    response = await model.generate_content_async(
        user_message,
        generation_config=genai.GenerationConfig(
            temperature=0.3,
            max_output_tokens=2000,
        )
    )

    return response.text


async def _generate_vertex(system_prompt: str, user_message: str) -> str:
    """Generate with Google Vertex AI"""
    import vertexai
    from vertexai.generative_models import GenerativeModel, GenerationConfig

    if not settings.VERTEX_PROJECT_ID:
        raise ValueError("VERTEX_PROJECT_ID is required for Vertex AI provider")

    vertexai.init(
        project=settings.VERTEX_PROJECT_ID,
        location=settings.VERTEX_LOCATION
    )

    model = GenerativeModel(
        model_name=settings.LLM_MODEL or "gemini-1.5-flash",
        system_instruction=system_prompt
    )

    response = await model.generate_content_async(
        user_message,
        generation_config=GenerationConfig(
            temperature=0.3,
            max_output_tokens=2000,
        )
    )

    return response.text


async def _generate_anthropic(system_prompt: str, user_message: str) -> str:
    """Generate with Anthropic Claude"""
    from anthropic import AsyncAnthropic

    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is required for Anthropic provider")

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = await client.messages.create(
        model=settings.LLM_MODEL or "claude-3-5-sonnet-20241022",
        max_tokens=2000,
        temperature=0.3,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )

    return response.content[0].text


async def _generate_openai(system_prompt: str, user_message: str) -> str:
    """Generate with OpenAI GPT"""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL or "gpt-4o-mini",
        max_tokens=2000,
        temperature=0.3,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    )

    return response.choices[0].message.content


# =============================================================================
# Streaming LLM Functions
# =============================================================================

async def stream_with_llm(system_prompt: str, user_message: str):
    """Stream response using configured LLM provider"""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "gemini":
        async for chunk in _stream_gemini(system_prompt, user_message):
            yield chunk
    elif provider == "vertex":
        async for chunk in _stream_vertex(system_prompt, user_message):
            yield chunk
    elif provider == "anthropic":
        async for chunk in _stream_anthropic(system_prompt, user_message):
            yield chunk
    elif provider == "openai":
        async for chunk in _stream_openai(system_prompt, user_message):
            yield chunk
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


async def _stream_gemini(system_prompt: str, user_message: str):
    """Stream with Google Gemini"""
    import google.generativeai as genai

    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is required for Gemini provider")

    genai.configure(api_key=settings.GEMINI_API_KEY)

    model = genai.GenerativeModel(
        model_name=settings.LLM_MODEL or "gemini-1.5-flash",
        system_instruction=system_prompt
    )

    response = await model.generate_content_async(
        user_message,
        generation_config=genai.GenerationConfig(
            temperature=0.3,
            max_output_tokens=2000,
        ),
        stream=True
    )

    async for chunk in response:
        if chunk.text:
            yield chunk.text


async def _stream_vertex(system_prompt: str, user_message: str):
    """Stream with Google Vertex AI"""
    import vertexai
    from vertexai.generative_models import GenerativeModel, GenerationConfig

    if not settings.VERTEX_PROJECT_ID:
        raise ValueError("VERTEX_PROJECT_ID is required for Vertex AI provider")

    vertexai.init(
        project=settings.VERTEX_PROJECT_ID,
        location=settings.VERTEX_LOCATION
    )

    model = GenerativeModel(
        model_name=settings.LLM_MODEL or "gemini-1.5-flash",
        system_instruction=system_prompt
    )

    response = await model.generate_content_async(
        user_message,
        generation_config=GenerationConfig(
            temperature=0.3,
            max_output_tokens=2000,
        ),
        stream=True
    )

    async for chunk in response:
        if chunk.text:
            yield chunk.text


async def _stream_anthropic(system_prompt: str, user_message: str):
    """Stream with Anthropic Claude"""
    from anthropic import AsyncAnthropic

    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is required for Anthropic provider")

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async with client.messages.stream(
        model=settings.LLM_MODEL or "claude-3-5-sonnet-20241022",
        max_tokens=2000,
        temperature=0.3,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def _stream_openai(system_prompt: str, user_message: str):
    """Stream with OpenAI GPT"""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    stream = await client.chat.completions.create(
        model=settings.LLM_MODEL or "gpt-4o-mini",
        max_tokens=2000,
        temperature=0.3,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        stream=True
    )

    async for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


# =============================================================================
# Enums and Filter Models
# =============================================================================

class SearchMode(str, Enum):
    """Search mode for queries"""
    SEMANTIC = "semantic"  # Vector similarity only
    KEYWORD = "keyword"    # Keyword matching only
    HYBRID = "hybrid"      # Combined semantic + keyword


class SearchFilters(BaseModel):
    """Filters for search queries"""
    file_types: Optional[List[str]] = Field(None, description="Filter by file extensions (e.g., ['pdf', 'docx'])")
    folder_path: Optional[str] = Field(None, description="Filter by folder path prefix")
    date_from: Optional[datetime] = Field(None, description="Filter documents indexed after this date")
    date_to: Optional[datetime] = Field(None, description="Filter documents indexed before this date")


# =============================================================================
# Request/Response Models
# =============================================================================

class QueryRequest(BaseModel):
    """RAG query request"""
    query: str = Field(..., description="User question", min_length=1, max_length=2000)
    connection_id: Optional[str] = Field(None, description="Filter by connection")
    top_k: int = Field(10, description="Number of chunks to retrieve", ge=1, le=50)
    include_sources: bool = Field(True, description="Include source citations")
    stream: bool = Field(False, description="Stream response")
    mode: SearchMode = Field(SearchMode.SEMANTIC, description="Search mode")
    filters: Optional[SearchFilters] = Field(None, description="Advanced filters")


class SourceCitation(BaseModel):
    """Source citation in response"""
    index: int
    document_name: str
    document_id: str
    chunk_id: str
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    web_url: Optional[str] = None
    excerpt: str
    score: float


class QueryResponse(BaseModel):
    """RAG query response"""
    query: str
    answer: str
    sources: List[SourceCitation]
    timing: Dict[str, float]
    mode: str = "semantic"


class SearchRequest(BaseModel):
    """Semantic search request"""
    query: str = Field(..., min_length=1, max_length=2000)
    connection_id: Optional[str] = None
    top_k: int = Field(10, ge=1, le=100)
    mode: SearchMode = Field(SearchMode.SEMANTIC, description="Search mode")
    filters: Optional[SearchFilters] = Field(None, description="Advanced filters")


class SearchResult(BaseModel):
    """Search result"""
    chunk_id: str
    document_id: str
    document_name: str
    content: str
    score: float
    page_number: Optional[int] = None
    web_url: Optional[str] = None



@router.post("", response_model=QueryResponse)
async def rag_query(request: QueryRequest, req: Request, current_user: User = Depends(require_auth)):
    """
    Execute RAG query - retrieve relevant chunks and generate answer.
    
    Pipeline:
    1. Embed query
    2. Search vector store
    3. Build context from top results
    4. Generate answer with LLM
    5. Return answer with source citations
    """
    import time
    
    vector_store = req.app.state.vector_store
    embedder = TextEmbedder()
    timing = {}
    
    # 1. Embed query
    start = time.time()
    query_embedding = await embedder.embed_text(request.query)
    timing["embedding_ms"] = (time.time() - start) * 1000
    
    # Build filters dict from SearchFilters model (including date range)
    filters_dict = None
    if request.filters:
        filters_dict = {
            "file_types": request.filters.file_types,
            "folder_path": request.filters.folder_path,
            "date_from": request.filters.date_from,
            "date_to": request.filters.date_to,
        }

    # 2. Search vector store based on mode
    start = time.time()

    if request.mode == SearchMode.HYBRID:
        # Hybrid: combine semantic + keyword using RRF
        results = await vector_store.hybrid_search(
            query_embedding=query_embedding,
            query_text=request.query,
            top_k=request.top_k,
            connection_id=request.connection_id,
            filters=filters_dict
        )
    elif request.mode == SearchMode.KEYWORD:
        # Keyword-only search
        results = await vector_store.keyword_search(
            query_text=request.query,
            top_k=request.top_k,
            connection_id=request.connection_id,
            filters=filters_dict
        )
    else:
        # Default: semantic search
        results = await vector_store.search(
            query_embedding=query_embedding,
            top_k=request.top_k,
            connection_id=request.connection_id,
            filters=filters_dict
        )

    timing["retrieval_ms"] = (time.time() - start) * 1000
    
    if not results:
        return QueryResponse(
            query=request.query,
            answer="ไม่พบข้อมูลที่เกี่ยวข้องกับคำถามนี้ในฐานข้อมูล",
            sources=[],
            timing=timing
        )
    
    # 3. Build context with improved formatting
    context_parts = []
    sources = []
    
    for idx, result in enumerate(results, 1):
        # Build a rich context block
        section_info = f" > {result.section_title}" if result.section_title else ""
        page_info = f" (Page {result.page_number})" if result.page_number else ""
        relevance = f"{result.score:.0%}"
        
        context_parts.append(
            f"[{idx}] 📄 {result.document_name}{section_info}{page_info}\n"
            f"    Relevance: {relevance}\n"
            f"    Content: {result.content}\n"
        )
        
        # Build cleaner excerpt
        excerpt = result.content.strip()
        if len(excerpt) > 250:
            # Try to cut at sentence boundary
            cut_point = excerpt[:250].rfind('. ')
            if cut_point > 100:
                excerpt = excerpt[:cut_point + 1]
            else:
                excerpt = excerpt[:247] + "..."
        
        sources.append(SourceCitation(
            index=idx,
            document_name=result.document_name,
            document_id=result.document_id,
            chunk_id=result.id,
            page_number=result.page_number,
            section_title=result.section_title,
            web_url=result.web_url,
            excerpt=excerpt,
            score=round(result.score, 4)
        ))
    
    context = "\n".join(context_parts)
    
    # 4. Generate answer with LLM
    start = time.time()

    system_prompt = """คุณเป็นผู้ช่วยที่ตอบคำถามโดยใช้ข้อมูลจาก context ที่ให้มา

กฎ:
1. ตอบคำถามโดยใช้ข้อมูลจาก context เท่านั้น
2. ถ้าไม่มีข้อมูลเพียงพอ ให้บอกตรงๆ
3. อ้างอิงแหล่งที่มาโดยใช้ [1], [2] ตามหมายเลขใน context
4. ตอบเป็นภาษาเดียวกับคำถาม
5. ตอบกระชับและตรงประเด็น"""

    user_message = f"""Context:
{context}

คำถาม: {request.query}

ตอบโดยอ้างอิง [หมายเลข] ของแหล่งที่มา:"""

    answer = await generate_with_llm(system_prompt, user_message)
    timing["generation_ms"] = (time.time() - start) * 1000
    timing["total_ms"] = sum(timing.values())
    
    # 5. Filter sources to only those cited
    import re
    cited_indices = set(int(m) for m in re.findall(r'\[(\d+)\]', answer))
    cited_sources = [s for s in sources if s.index in cited_indices]
    
    return QueryResponse(
        query=request.query,
        answer=answer,
        sources=cited_sources if request.include_sources else [],
        timing=timing,
        mode=request.mode.value
    )


@router.post("/search", response_model=List[SearchResult])
async def semantic_search(request: SearchRequest, req: Request, current_user: User = Depends(require_auth)):
    """
    Search for relevant chunks.

    Supports multiple modes:
    - semantic: Vector similarity search (default)
    - keyword: Full-text keyword matching
    - hybrid: Combined semantic + keyword using Reciprocal Rank Fusion
    """
    vector_store = req.app.state.vector_store
    embedder = TextEmbedder()

    # Build filters dict from SearchFilters model (including date range)
    filters_dict = None
    if request.filters:
        filters_dict = {
            "file_types": request.filters.file_types,
            "folder_path": request.filters.folder_path,
            "date_from": request.filters.date_from,
            "date_to": request.filters.date_to,
        }

    # Search based on mode
    if request.mode == SearchMode.HYBRID:
        # Hybrid needs both embedding and text
        query_embedding = await embedder.embed_text(request.query)
        results = await vector_store.hybrid_search(
            query_embedding=query_embedding,
            query_text=request.query,
            top_k=request.top_k,
            connection_id=request.connection_id,
            filters=filters_dict
        )
    elif request.mode == SearchMode.KEYWORD:
        # Keyword search doesn't need embedding
        results = await vector_store.keyword_search(
            query_text=request.query,
            top_k=request.top_k,
            connection_id=request.connection_id,
            filters=filters_dict
        )
    else:
        # Semantic search (default)
        query_embedding = await embedder.embed_text(request.query)
        results = await vector_store.search(
            query_embedding=query_embedding,
            top_k=request.top_k,
            connection_id=request.connection_id,
            filters=filters_dict
        )

    return [
        SearchResult(
            chunk_id=r.id,
            document_id=r.document_id,
            document_name=r.document_name,
            content=r.content,
            score=r.score,
            page_number=r.page_number,
            web_url=r.web_url
        )
        for r in results
    ]


@router.post("/stream")
async def rag_query_stream(request: QueryRequest, req: Request, current_user: User = Depends(require_auth)):
    """
    Streaming RAG query - streams the answer as it's generated.
    """
    vector_store = req.app.state.vector_store
    embedder = TextEmbedder()
    
    # Embed and search
    query_embedding = await embedder.embed_text(request.query)
    results = await vector_store.search(
        query_embedding=query_embedding,
        top_k=request.top_k,
        connection_id=request.connection_id
    )
    
    if not results:
        async def no_results():
            yield f"data: {json.dumps({'type': 'error', 'message': 'No relevant documents found'})}\n\n"
        return StreamingResponse(no_results(), media_type="text/event-stream")
    
    # Build context
    context_parts = []
    sources = []
    
    for idx, result in enumerate(results, 1):
        context_parts.append(
            f"[{idx}] {result.document_name}: {result.content}"
        )
        sources.append({
            "index": idx,
            "document_name": result.document_name,
            "document_id": result.document_id,
            "web_url": result.web_url
        })
    
    context = "\n\n".join(context_parts)
    
    # Stream response
    async def generate():
        # Send sources first
        yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"

        system_prompt = "ตอบคำถามโดยใช้ข้อมูลจาก context อ้างอิงด้วย [หมายเลข]"
        user_message = f"Context:\n{context}\n\nQuestion: {request.query}"

        try:
            async for text in stream_with_llm(system_prompt, user_message):
                yield f"data: {json.dumps({'type': 'content', 'text': text})}\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/stats")
async def get_stats(req: Request, current_user: User = Depends(require_auth)):
    """Get vector store statistics"""
    vector_store = req.app.state.vector_store
    stats = await vector_store.get_collection_stats()
    return stats
