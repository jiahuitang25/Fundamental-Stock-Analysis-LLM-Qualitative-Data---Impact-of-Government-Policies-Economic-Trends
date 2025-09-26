"""
RAG (Retrieval-Augmented Generation) Service for the Stock Analysis Application
"""

import logging
from typing import List, Dict, Any, Optional

# Fix OpenAI compatibility issue with llama-index
try:
    from openai.types.responses import ResponseTextAnnotationDeltaEvent
except ImportError:
    # Use ResponseTextDeltaEvent as fallback since ResponseTextAnnotationDeltaEvent doesn't exist
    from openai.types.responses import ResponseTextDeltaEvent
    ResponseTextAnnotationDeltaEvent = ResponseTextDeltaEvent
    
    # Add it to the openai module for compatibility
    import openai
    if not hasattr(openai.types.responses, 'ResponseTextAnnotationDeltaEvent'):
        openai.types.responses.ResponseTextAnnotationDeltaEvent = ResponseTextAnnotationDeltaEvent

from llama_index.core import VectorStoreIndex, Settings
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.tools import QueryEngineTool
from llama_index.agent.openai import OpenAIAgent
from llama_index.llms.openai import OpenAI
from llama_index.core.schema import Document
from llama_index.core.node_parser import SentenceSplitter
from config import Config

logger = logging.getLogger(__name__)

class RAGService:
    """Service for RAG operations and document processing"""
    
    def __init__(self):
        self.embed_model = OpenAIEmbedding(model=Config.MODEL_CONFIG['embedding_model'])
        self.llm = OpenAI(
            model=Config.MODEL_CONFIG['llm_model'],
            temperature=Config.MODEL_CONFIG['temperature']
        )
        Settings.embed_model = self.embed_model
        Settings.llm = self.llm
    
    def setup_rag(self, documents: List[Dict], embed_model_name: str = None, llm_model_name: str = None):
        """Setup RAG system with documents"""
        try:
            if not documents:
                logger.warning("No documents provided for RAG setup")
                return None
            
            # Convert documents to LlamaIndex format
            llama_docs = []
            for doc in documents:
                if isinstance(doc, dict):
                    content = doc.get('content', '') or doc.get('text', '') or str(doc)
                    metadata = doc.get('metadata', {})
                else:
                    content = str(doc)
                    metadata = {}
                
                if content.strip():
                    llama_doc = Document(text=content, metadata=metadata)
                    llama_docs.append(llama_doc)
            
            if not llama_docs:
                logger.warning("No valid documents found for RAG setup")
                return None
            
            # Create vector store index
            index = VectorStoreIndex.from_documents(llama_docs)
            
            # Create query engine
            query_engine = index.as_query_engine(
                response_mode="compact",
                similarity_top_k=5,
                verbose=True
            )
            
            logger.info(f"RAG system setup with {len(llama_docs)} documents")
            return query_engine
            
        except Exception as e:
            logger.error(f"Error setting up RAG: {e}")
            return None
    
    def setup_conversational_agent(self, documents: List[Dict], embed_model_name: str = None, 
                                 llm_model_name: str = None, conversation_context: Dict = None):
        """Setup conversational agent for chat-like interactions"""
        try:
            if not documents:
                logger.warning("No documents provided for conversational agent")
                return None
            
            # Process documents with chunking
            from utils.text_processing import process_documents_with_chunking
            chunked_docs = process_documents_with_chunking(
                documents, 
                chunk_size=Config.CHUNKING_CONFIG['chunk_size'],
                chunk_overlap=Config.CHUNKING_CONFIG['chunk_overlap']
            )
            
            # Convert to LlamaIndex documents
            llama_docs = []
            for doc in chunked_docs:
                content = doc.get('content', '')
                metadata = doc.get('metadata', {})
                if content.strip():
                    llama_doc = Document(text=content, metadata=metadata)
                    llama_docs.append(llama_doc)
            
            if not llama_docs:
                logger.warning("No valid documents after chunking")
                return None
            
            # Create vector store index
            index = VectorStoreIndex.from_documents(llama_docs)
            
            # Create query engine tool
            query_engine = index.as_query_engine(
                response_mode="compact",
                similarity_top_k=5
            )
            
            query_engine_tool = QueryEngineTool.from_defaults(
                query_engine=query_engine,
                name="stock_analysis_tool",
                description="Tool for analyzing stock market data, news, and financial information"
            )
            
            # Build context information
            context_info = ""
            if conversation_context:
                if conversation_context.get('ticker'):
                    context_info += f"Current ticker being discussed: {conversation_context['ticker']}\n"
                if conversation_context.get('summary'):
                    context_info += f"Previous analysis summary: {conversation_context['summary'][:200]}...\n"
                if conversation_context.get('actionable_insights'):
                    context_info += f"Previous insights: {', '.join(conversation_context['actionable_insights'][:3])}\n"
            
            # Create conversational agent
            agent = OpenAIAgent.from_tools(
                [query_engine_tool],
                system_prompt=f"""You are a helpful stock analysis assistant. Provide clear, conversational responses to user questions about stocks, markets, and financial analysis.

CONVERSATIONAL APPROACH:
- Be friendly and approachable while maintaining professionalism
- Ask clarifying questions when needed
- Provide context-aware responses that build on previous conversation
- Use simple language that retail investors can understand
- Be encouraging and supportive

RESPONSE GUIDELINES:
- Start with a direct answer to the user's question
- Provide relevant details and context
- Include actionable insights when appropriate
- Reference previous conversation when relevant
- End with follow-up questions or suggestions

{context_info}

Remember: You are having a conversation with an investor. Be helpful, clear, and engaging."""
            )
            
            logger.info("Conversational agent setup completed")
            return agent
            
        except Exception as e:
            logger.error(f"Error setting up conversational agent: {e}")
            return None
    
    def setup_analytical_agent(self, documents: List[Dict], conversation_context: Dict,
                              embed_model_name: str = None, llm_model_name: str = None):
        """Setup analytical agent for detailed analysis"""
        try:
            if not documents:
                logger.warning("No documents provided for analytical agent")
                return None
            
            # Process documents with semantic chunking
            from utils.text_processing import process_documents_with_semantic_chunking
            chunked_docs = process_documents_with_semantic_chunking(
                documents, 
                chunk_size=800, 
                chunk_overlap=100
            )
            
            # Convert to LlamaIndex documents
            llama_docs = []
            for doc in chunked_docs:
                content = doc.get('content', '')
                metadata = doc.get('metadata', {})
                if content.strip():
                    llama_doc = Document(text=content, metadata=metadata)
                    llama_docs.append(llama_doc)
            
            if not llama_docs:
                logger.warning("No valid documents after semantic chunking")
                return None
            
            # Create vector store index
            index = VectorStoreIndex.from_documents(llama_docs)
            
            # Create query engine tool
            query_engine = index.as_query_engine(
                response_mode="compact",
                similarity_top_k=8
            )
            
            query_engine_tool = QueryEngineTool.from_defaults(
                query_engine=query_engine,
                name="analytical_tool",
                description="Comprehensive tool for detailed stock market analysis, risk assessment, and investment insights"
            )
            
            # Build context information
            context_info = ""
            if conversation_context:
                if conversation_context.get('ticker'):
                    context_info += f"Current ticker being analyzed: {conversation_context['ticker']}\n"
                if conversation_context.get('summary'):
                    context_info += f"Previous analysis: {conversation_context['summary'][:300]}...\n"
                if conversation_context.get('actionable_insights'):
                    context_info += f"Previous insights: {', '.join(conversation_context['actionable_insights'][:5])}\n"
                if conversation_context.get('risk_score'):
                    context_info += f"Previous risk assessment: {conversation_context['risk_score']}\n"
            
            # Create analytical agent
            agent = OpenAIAgent.from_tools(
                [query_engine_tool],
                system_prompt=f"""You are a professional stock analyst providing comprehensive, analytical responses to investment questions for retail investors. Your responses should be detailed, structured, and maintain context across the conversation.

ANALYTICAL APPROACH:
- Provide thorough, well-reasoned analysis that builds upon previous context
- Maintain analytical depth while being accessible to retail investors
- Reference previous discussions when relevant to provide continuity
- Structure responses logically with clear reasoning and evidence
- Balance quantitative insights with qualitative analysis
- Address both opportunities and risks comprehensively

RESPONSE STRUCTURE:
- Start with a clear, analytical statement addressing the specific question
- Provide detailed analysis with supporting evidence from sources
- Reference previous context when relevant ("As we discussed earlier...", "Building on the previous analysis...")
- Include multiple perspectives and considerations
- Conclude with actionable insights and next steps for consideration

CONTEXT AWARENESS:
- Always consider the conversation history and previous analysis
- Build upon earlier insights rather than starting from scratch
- Maintain thematic consistency throughout the conversation
- Reference specific tickers, sectors, or topics from previous exchanges when relevant

ANALYTICAL STANDARDS:
- Use professional, analytical language appropriate for investment analysis
- Provide specific, actionable insights rather than generic advice
- Support analysis with relevant market data and policy information
- Consider multiple time horizons (short-term, medium-term, long-term)
- Address both fundamental and technical considerations when relevant

{context_info}

Remember: You are continuing an analytical conversation. Build upon previous context, maintain analytical rigor, and provide comprehensive insights that help investors make informed decisions."""
            )
            
            logger.info("Analytical agent setup completed")
            return agent
            
        except Exception as e:
            logger.error(f"Error setting up analytical agent: {e}")
            return None
    
    def extract_analysis(self, response_text: str) -> Dict[str, Any]:
        """Extract structured analysis from LLM response"""
        try:
            logger.info("=== RAW LLM RESPONSE ===")
            logger.info(response_text)
            logger.info("========================")
            
            # Initialize default values
            risk_score = None
            risk_explanation = None
            summary = None
            insights = []
            
            # Try to extract risk score
            import re
            risk_patterns = [
                r'risk\s*score[:\s]*(\d+(?:\.\d+)?)',
                r'risk\s*level[:\s]*(\d+(?:\.\d+)?)',
                r'risk[:\s]*(\d+(?:\.\d+)?)',
                r'(\d+(?:\.\d+)?)\s*out\s*of\s*5',
                r'(\d+(?:\.\d+)?)/5'
            ]
            
            for pattern in risk_patterns:
                match = re.search(pattern, response_text, re.IGNORECASE)
                if match:
                    try:
                        risk_score = float(match.group(1))
                        if 1 <= risk_score <= 5:
                            break
                    except ValueError:
                        continue
            
            # Try to extract summary
            summary_patterns = [
                r'summary[:\s]*(.+?)(?:\n\n|\n[A-Z]|$)',
                r'overview[:\s]*(.+?)(?:\n\n|\n[A-Z]|$)',
                r'analysis[:\s]*(.+?)(?:\n\n|\n[A-Z]|$)'
            ]
            
            for pattern in summary_patterns:
                match = re.search(pattern, response_text, re.IGNORECASE | re.DOTALL)
                if match:
                    summary = match.group(1).strip()
                    break
            
            # Try to extract insights
            insights_patterns = [
                r'insights?[:\s]*(.+?)(?:\n\n|\n[A-Z]|$)',
                r'key\s*points?[:\s]*(.+?)(?:\n\n|\n[A-Z]|$)',
                r'recommendations?[:\s]*(.+?)(?:\n\n|\n[A-Z]|$)'
            ]
            
            for pattern in insights_patterns:
                match = re.search(pattern, response_text, re.IGNORECASE | re.DOTALL)
                if match:
                    insights_text = match.group(1).strip()
                    # Split into individual insights
                    insights = [insight.strip() for insight in insights_text.split('\n') if insight.strip()]
                    break
            
            # If no structured extraction worked, use the full response as summary
            if not summary:
                summary = response_text[:500] + "..." if len(response_text) > 500 else response_text
            
            return {
                'risk_score': risk_score,
                'risk_explanation': risk_explanation,
                'summary': summary,
                'insights': insights,
                'raw_response': response_text
            }
            
        except Exception as e:
            logger.error(f"Error extracting analysis: {e}")
            return {
                'risk_score': None,
                'risk_explanation': None,
                'summary': response_text,
                'insights': [],
                'raw_response': response_text
            }
