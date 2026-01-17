# app/processing/chunker.py
"""Text chunking strategies for RAG"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import re
import tiktoken
import logging

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A text chunk with metadata"""
    content: str
    index: int
    start_char: int
    end_char: int
    token_count: int
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    metadata: Dict[str, Any] = None


class TextChunker:
    """
    Split text into overlapping chunks optimized for RAG retrieval.
    """
    
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        min_chunk_size: int = 100
    ):
        """
        Args:
            chunk_size: Target chunk size in tokens
            chunk_overlap: Overlap between chunks in tokens
            min_chunk_size: Minimum chunk size (skip smaller)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.tokenizer.encode(text))
    
    def chunk_text(
        self,
        text: str,
        metadata: Optional[Dict] = None
    ) -> List[Chunk]:
        """
        Split text into chunks using recursive splitting.
        
        Tries to split on natural boundaries:
        1. Double newlines (paragraphs)
        2. Single newlines
        3. Sentences
        4. Words
        """
        if not text or not text.strip():
            return []
        
        # Clean text
        text = self._clean_text(text)
        
        # Extract page markers if present
        page_map = self._extract_page_markers(text)
        text = self._remove_page_markers(text)
        
        # Recursive split
        chunks = self._recursive_split(text)
        
        # Create Chunk objects with metadata
        result = []
        char_offset = 0
        
        for idx, chunk_text in enumerate(chunks):
            token_count = self.count_tokens(chunk_text)
            
            # Skip too small chunks
            if token_count < self.min_chunk_size and idx < len(chunks) - 1:
                # Merge with next chunk if possible
                continue
            
            # Find page number
            page_num = self._find_page_number(char_offset, page_map)
            
            chunk = Chunk(
                content=chunk_text,
                index=len(result),
                start_char=char_offset,
                end_char=char_offset + len(chunk_text),
                token_count=token_count,
                page_number=page_num,
                section_title=self._extract_section_title(chunk_text),
                metadata=metadata
            )
            
            result.append(chunk)
            char_offset += len(chunk_text)
        
        logger.info(f"Created {len(result)} chunks from {len(text)} chars")
        return result
    
    def _recursive_split(self, text: str) -> List[str]:
        """Recursively split text into chunks"""
        # Separators in order of preference
        separators = [
            "\n\n",      # Paragraphs
            "\n",        # Lines
            ". ",        # Sentences
            "! ",
            "? ",
            "; ",
            ", ",        # Clauses
            " ",         # Words
            ""           # Characters (last resort)
        ]
        
        return self._split_recursive(text, separators)
    
    def _split_recursive(
        self,
        text: str,
        separators: List[str],
        depth: int = 0
    ) -> List[str]:
        """Recursive splitting implementation"""
        # Base case: text fits in one chunk
        if self.count_tokens(text) <= self.chunk_size:
            return [text.strip()] if text.strip() else []
        
        # No more separators, force split
        if not separators:
            return self._force_split(text)
        
        separator = separators[0]
        remaining_separators = separators[1:]
        
        # Split on current separator
        if separator:
            splits = text.split(separator)
        else:
            # Character-level split
            return self._force_split(text)
        
        # Merge splits into chunks
        chunks = []
        current_chunk = ""
        
        for i, split in enumerate(splits):
            # Add separator back (except for first split)
            if current_chunk and separator:
                test_chunk = current_chunk + separator + split
            else:
                test_chunk = split
            
            if self.count_tokens(test_chunk) <= self.chunk_size:
                current_chunk = test_chunk
            else:
                # Current chunk is full
                if current_chunk:
                    # Check if current chunk needs further splitting
                    if self.count_tokens(current_chunk) > self.chunk_size:
                        chunks.extend(
                            self._split_recursive(current_chunk, remaining_separators, depth + 1)
                        )
                    else:
                        chunks.append(current_chunk.strip())
                
                # Start new chunk (may need recursive split)
                if self.count_tokens(split) > self.chunk_size:
                    chunks.extend(
                        self._split_recursive(split, remaining_separators, depth + 1)
                    )
                    current_chunk = ""
                else:
                    current_chunk = split
        
        # Don't forget last chunk
        if current_chunk:
            if self.count_tokens(current_chunk) > self.chunk_size:
                chunks.extend(
                    self._split_recursive(current_chunk, remaining_separators, depth + 1)
                )
            else:
                chunks.append(current_chunk.strip())
        
        # Add overlap between chunks
        return self._add_overlap(chunks)
    
    def _force_split(self, text: str) -> List[str]:
        """Force split text by token count"""
        tokens = self.tokenizer.encode(text)
        chunks = []
        
        for i in range(0, len(tokens), self.chunk_size - self.chunk_overlap):
            chunk_tokens = tokens[i:i + self.chunk_size]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            if chunk_text.strip():
                chunks.append(chunk_text.strip())
        
        return chunks
    
    def _add_overlap(self, chunks: List[str]) -> List[str]:
        """Add overlapping context between chunks"""
        if len(chunks) <= 1 or self.chunk_overlap == 0:
            return chunks
        
        result = []
        
        for i, chunk in enumerate(chunks):
            if i == 0:
                result.append(chunk)
                continue
            
            # Get overlap from previous chunk
            prev_chunk = chunks[i - 1]
            prev_tokens = self.tokenizer.encode(prev_chunk)
            
            if len(prev_tokens) > self.chunk_overlap:
                overlap_tokens = prev_tokens[-self.chunk_overlap:]
                overlap_text = self.tokenizer.decode(overlap_tokens)
                
                # Add overlap prefix
                chunk_with_overlap = overlap_text.strip() + " " + chunk
                result.append(chunk_with_overlap)
            else:
                result.append(chunk)
        
        return result
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        # Normalize whitespace
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\r', '\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
    
    def _extract_page_markers(self, text: str) -> Dict[int, int]:
        """Extract [Page N] markers and their positions"""
        page_map = {}
        for match in re.finditer(r'\[Page (\d+)\]', text):
            page_num = int(match.group(1))
            page_map[match.start()] = page_num
        return page_map
    
    def _remove_page_markers(self, text: str) -> str:
        """Remove [Page N] markers from text"""
        return re.sub(r'\[Page \d+\]\n?', '', text)
    
    def _find_page_number(
        self,
        char_offset: int,
        page_map: Dict[int, int]
    ) -> Optional[int]:
        """Find page number for a character offset"""
        if not page_map:
            return None
        
        current_page = None
        for pos, page in sorted(page_map.items()):
            if pos <= char_offset:
                current_page = page
            else:
                break
        
        return current_page
    
    def _extract_section_title(self, text: str) -> Optional[str]:
        """Extract section title from chunk if present"""
        # Look for markdown headers
        match = re.match(r'^#+\s+(.+?)$', text, re.MULTILINE)
        if match:
            return match.group(1).strip()
        
        # Look for title-case first line
        first_line = text.split('\n')[0].strip()
        if len(first_line) < 100 and first_line.istitle():
            return first_line
        
        return None
