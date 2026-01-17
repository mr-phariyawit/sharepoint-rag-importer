# app/processing/embedder.py
"""Text embedding generation"""

from typing import List
import openai
from tenacity import retry, stop_after_attempt, wait_exponential
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class TextEmbedder:
    """
    Generate embeddings using OpenAI API.
    """
    
    def __init__(
        self,
        model: str = None,
        dimensions: int = None
    ):
        self.model = model or settings.EMBEDDING_MODEL
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSIONS
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text"""
        params = {
            "model": self.model,
            "input": text,
        }
        # Dimensions param removed due to library version incompatibility
            
        response = await self.client.embeddings.create(**params)
        return response.data[0].embedding
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            batch_size: Maximum texts per API call
            
        Returns:
            List of embeddings in same order as input
        """
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            params = {
                "model": self.model,
                "input": batch,
            }
            # Dimensions param removed due to library version incompatibility
                
            response = await self.client.embeddings.create(**params)
            
            # Sort by index to maintain order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            batch_embeddings = [d.embedding for d in sorted_data]
            
            all_embeddings.extend(batch_embeddings)
            
            logger.info(f"Embedded batch {i//batch_size + 1}: {len(batch)} texts")
        
        return all_embeddings
    
    def count_tokens(self, text: str) -> int:
        """Estimate token count for pricing"""
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
