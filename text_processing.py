"""
Text processing utilities for the Stock Analysis Application
"""

import re
import logging
from typing import List, Dict, Any, Optional
from scipy.spatial.distance import cosine
from langchain.text_splitter import RecursiveCharacterTextSplitter, SpacyTextSplitter
from llama_index.core.node_parser import SentenceSplitter
import spacy

logger = logging.getLogger(__name__)

def cosine_similarity(vec1, vec2):
    """Calculate cosine similarity between two vectors"""
    return 1 - cosine(vec1, vec2)

def semantic_chunk_text(text, chunk_size=None, chunk_overlap=None):
    """
    Perform semantic chunking on text using spaCy for better sentence boundary detection
    """
    try:
        # Load spaCy model
        nlp = spacy.load("en_core_web_sm")
        
        # Default chunking parameters
        if chunk_size is None:
            chunk_size = 768
        if chunk_overlap is None:
            chunk_overlap = 128
        
        # Use spaCy text splitter for better sentence boundary detection
        text_splitter = SpacyTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            pipeline="en_core_web_sm"
        )
        
        # Split the text
        chunks = text_splitter.split_text(text)
        
        logger.info(f"Semantic chunking created {len(chunks)} chunks from text of length {len(text)}")
        return chunks
        
    except Exception as e:
        logger.error(f"Error in semantic chunking: {e}")
        # Fallback to recursive character splitter
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size or 768,
            chunk_overlap=chunk_overlap or 128,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        return text_splitter.split_text(text)

def process_documents_with_semantic_chunking(raw_documents, chunk_size=None, chunk_overlap=None):
    """
    Process documents with semantic chunking for better context preservation
    """
    try:
        chunked_documents = []
        
        for doc in raw_documents:
            if isinstance(doc, dict):
                content = doc.get('content', '') or doc.get('text', '') or str(doc)
            else:
                content = str(doc)
            
            if not content.strip():
                continue
                
            # Perform semantic chunking
            chunks = semantic_chunk_text(content, chunk_size, chunk_overlap)
            
            # Create document objects for each chunk
            for i, chunk in enumerate(chunks):
                if chunk.strip():
                    chunked_doc = {
                        'content': chunk.strip(),
                        'metadata': doc.get('metadata', {}) if isinstance(doc, dict) else {},
                        'chunk_index': i,
                        'total_chunks': len(chunks),
                        'original_length': len(content)
                    }
                    chunked_documents.append(chunked_doc)
        
        logger.info(f"Processed {len(raw_documents)} documents into {len(chunked_documents)} semantic chunks")
        return chunked_documents
        
    except Exception as e:
        logger.error(f"Error in semantic document processing: {e}")
        return raw_documents

def process_documents_with_chunking(raw_documents, chunk_size=None, chunk_overlap=None):
    """
    Process documents with standard chunking
    """
    try:
        chunk_size = chunk_size or 768
        chunk_overlap = chunk_overlap or 128
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        chunked_documents = []
        
        for doc in raw_documents:
            if isinstance(doc, dict):
                content = doc.get('content', '') or doc.get('text', '') or str(doc)
            else:
                content = str(doc)
            
            if not content.strip():
                continue
                
            chunks = text_splitter.split_text(content)
            
            for i, chunk in enumerate(chunks):
                if chunk.strip():
                    chunked_doc = {
                        'content': chunk.strip(),
                        'metadata': doc.get('metadata', {}) if isinstance(doc, dict) else {},
                        'chunk_index': i,
                        'total_chunks': len(chunks)
                    }
                    chunked_documents.append(chunked_doc)
        
        return chunked_documents
        
    except Exception as e:
        logger.error(f"Error in document chunking: {e}")
        return raw_documents

def extract_content(json_data):
    """Extract content from various JSON structures"""
    if isinstance(json_data, dict):
        # Try different possible content fields
        for field in ['content', 'text', 'body', 'description', 'summary']:
            if field in json_data and json_data[field]:
                return str(json_data[field])
        
        # If no content field found, convert entire dict to string
        return str(json_data)
    elif isinstance(json_data, list):
        # Join list items
        return ' '.join(str(item) for item in json_data)
    else:
        return str(json_data)

def format_markdown_response(response_text):
    """Format response text with markdown support"""
    try:
        import markdown
        # Convert markdown to HTML
        html = markdown.markdown(response_text, extensions=['tables', 'fenced_code'])
        return html
    except Exception as e:
        logger.error(f"Error formatting markdown: {e}")
        return response_text

def analyze_chunking_performance(chunked_documents):
    """Analyze the performance of chunking"""
    if not chunked_documents:
        return {"error": "No documents to analyze"}
    
    total_chunks = len(chunked_documents)
    chunk_sizes = [len(doc.get('content', '')) for doc in chunked_documents]
    
    return {
        "total_chunks": total_chunks,
        "average_chunk_size": sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0,
        "min_chunk_size": min(chunk_sizes) if chunk_sizes else 0,
        "max_chunk_size": max(chunk_sizes) if chunk_sizes else 0,
        "chunks_with_metadata": sum(1 for doc in chunked_documents if doc.get('metadata')),
        "semantic_chunks": sum(1 for doc in chunked_documents if 'chunk_index' in doc)
    }

def filter_high_quality_contexts(documents, query, min_score_threshold=0.3):
    """Filter documents based on quality and relevance"""
    if not documents:
        return []
    
    filtered_docs = []
    for doc in documents:
        content = doc.get('content', '')
        if not content or len(content.strip()) < 50:
            continue
            
        # Basic quality checks
        if len(content.split()) < 10:  # Too short
            continue
            
        # Check for relevance (basic keyword matching)
        query_words = set(query.lower().split())
        content_words = set(content.lower().split())
        overlap = len(query_words.intersection(content_words))
        
        if overlap > 0 or len(content) > 200:  # Has some relevance or is substantial
            filtered_docs.append(doc)
    
    return filtered_docs

def consolidate_chunked_sources(retrieved_chunks):
    """Consolidate chunked sources to avoid duplication"""
    if not retrieved_chunks:
        return []
    
    # Group chunks by source
    source_groups = {}
    for chunk in retrieved_chunks:
        source = chunk.get('source', 'unknown')
        if source not in source_groups:
            source_groups[source] = []
        source_groups[source].append(chunk)
    
    # Consolidate each source group
    consolidated_sources = []
    for source, chunks in source_groups.items():
        if len(chunks) == 1:
            consolidated_sources.append(chunks[0])
        else:
            # Combine chunks from same source
            combined_content = ' '.join(chunk.get('content', '') for chunk in chunks)
            consolidated_source = {
                'source': source,
                'content': combined_content,
                'chunk_count': len(chunks),
                'metadata': chunks[0].get('metadata', {})
            }
            consolidated_sources.append(consolidated_source)
    
    return consolidated_sources
