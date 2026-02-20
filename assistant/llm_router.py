"""
LLM Router - Handles local (Ollama) and online (Groq, Nvidia, OpenRouter, Gemini) models
"""

import ollama
from google import genai
from groq import Groq
from openai import OpenAI
from typing import Optional, List, Dict, Any
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    OLLAMA_MODEL,
    GEMINI_MODEL,
    OPENROUTER_MODEL,
    NVIDIA_MODEL,
    LMSTUDIO_MODEL,
    MEMORY_MIN_CONFIDENCE,
    MEMORY_MAX_RESULTS,
)
from assistant.personality import SYSTEM_PROMPT
from assistant.fact_extractor import FactExtractor
from assistant.interfaces import ILLMProvider


class LLMRouter(ILLMProvider):
    """Routes between multiple LLM providers with fallback logic cache"""

    def __init__(self, conversation_memory=None, long_term_memory=None, prefer_local: bool = True):
        self.prefer_local = prefer_local
        self.conversation_memory = conversation_memory
        self.long_term_memory = long_term_memory
        
        self._ollama_available: Optional[bool] = None
        self._ollama_model_name = OLLAMA_MODEL
        # FactExtractor needs both memory types
        self.fact_extractor = FactExtractor(
            self, 
            conversation_memory=self.conversation_memory, 
            long_term_memory=self.long_term_memory
        ) if self.long_term_memory else None

        # Clients
        self._gemini_client: Optional[genai.Client] = None
        self._groq_client: Optional[Groq] = None
        self._openrouter_client: Optional[OpenAI] = None
        self._nvidia_client: Optional[OpenAI] = None
        self._lmstudio_client: Optional[OpenAI] = None
        self._lmstudio_available: Optional[bool] = None

    # ... (check_ollama, check_lmstudio methods) ...
    
    def _check_ollama(self) -> bool:
        """Check if Ollama is running"""
        if self._ollama_available is not None:
            return self._ollama_available
        try:
            ollama.list()
            self._ollama_available = True
        except:
            self._ollama_available = False
        return self._ollama_available

    def _check_lmstudio(self) -> bool:
        """Check if LM Studio is running"""
        if self._lmstudio_available is not None:
            return self._lmstudio_available
        try:
            # Simple connection check
            import requests
            requests.get(f"{LMSTUDIO_HOST}/v1/models", timeout=1)
            self._lmstudio_available = True
            
            # Init client on first success
            if not self._lmstudio_client:
                 self._lmstudio_client = OpenAI(base_url=f"{LMSTUDIO_HOST}/v1", api_key="lm-studio")
                 
        except:
            self._lmstudio_available = False
        return self._lmstudio_available

    def _configure_online(self):
        """Initialize online providers if keys exist"""
        if not self._groq_client and os.getenv("GROQ_API_KEY"):
            self._groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        
        if not self._gemini_client and os.getenv("GEMINI_API_KEY"):
            self._gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        if not self._nvidia_client and os.getenv("NVIDIA_API_KEY"):
             self._nvidia_client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=os.getenv("NVIDIA_API_KEY")
            )
            
        if not self._openrouter_client and os.getenv("OPENROUTER_API_KEY"):
            self._openrouter_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.getenv("OPENROUTER_API_KEY"),
            )

    # Helper method for _check_ollama and others...
    # (Using the original methods, just truncated for replacement)

    def _build_messages(self, user_message: str, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Build message list with conversation history and relevant memories"""
        memory_prompt = ""

        # Search long-term memory for relevant context
        if self.long_term_memory:
            try:
                # Search for memories relevant to the current query
                relevant_memories = self.long_term_memory.search(
                    query=user_message,
                    limit=MEMORY_MAX_RESULTS,
                    min_confidence=MEMORY_MIN_CONFIDENCE
                )

                if relevant_memories:
                    memory_lines = []
                    for mem in relevant_memories:
                        memory_lines.append(f"- {mem.content}")
                    memory_prompt = "\n\nRELEVANT MEMORIES:\n" + "\n".join(memory_lines)
            except Exception:
                pass  

        # Build messages
        messages = [{"role": "system", "content": SYSTEM_PROMPT + memory_prompt}]

        # Load recent conversation history (provided by caller)
        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": user_message})
        return messages

    async def chat(
        self, user_message: str, history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Route message through available providers"""
        response = None
        self._configure_online()

        # Get Tools
        from assistant.skills_registry import registry
        tools = registry.get_tool_definitions()

        # 1. Ollama (Local - Speed/Primary) - Supports Tools
        if self.prefer_local and self._check_ollama():
            response = await self._chat_ollama(user_message, history, tools)

        # 2. LM Studio (Local - Reasoning/Fallback)
        if response is None and self.prefer_local and self._check_lmstudio():
            response = await self._chat_lmstudio(user_message, history)

        # 3. Groq (Fastest Cloud)
        if response is None and self._groq_client:
            response = await self._chat_groq(user_message, history)

        # 4. Nvidia (Strong Cloud)
        if response is None and self._nvidia_client:
            response = await self._chat_nvidia(user_message, history)

        # 5. OpenRouter (Aggregation)
        if response is None and self._openrouter_client:
            response = await self._chat_openrouter(user_message, history)

        # 6. Gemini (Google/Multimodal)
        if response is None and self._gemini_client:
            response = await self._chat_gemini(user_message, history)

        # Final Failure
        if response is None:
            return "All my brain connections are down. Please check your internet and API keys."

        # Fact Extraction (Async Side Effect)
        if self.fact_extractor:
            try:
                # Fire and forget task
                asyncio.create_task(self.fact_extractor.extract_facts_async(user_message, response))
            except Exception as e:
                print(f"   [!] Fact Extraction Trigger Failed: {e}")
            
        return response

    async def _chat_lmstudio(self, user_message: str, history: List[Dict[str, str]]) -> Optional[str]:
        """Chat with LM Studio (OpenAI-compatible API)"""
        if not self._lmstudio_client:
            return None
        try:
            messages = self._build_messages(user_message, history)
            # Run blocking call in thread
            completion = await asyncio.to_thread(
                self._lmstudio_client.chat.completions.create,
                model=LMSTUDIO_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"   [!] LM Studio: {e}")
            self._lmstudio_available = False
            return None

    async def _chat_ollama(self, user_message: str, history: List[Dict[str, str]], tools: List[Dict] = None) -> Optional[str]:
        try:
            messages = self._build_messages(user_message, history)
            
            # 1. Call Ollama
            response = await asyncio.to_thread(
                ollama.chat,
                model=self._ollama_model_name,
                messages=messages,
                tools=tools if tools else None
            )
            
            message = response["message"]
            
            # 2. Check for Tool Calls
            if message.get("tool_calls"):
                print(f"   🛠️ Tool Calls detected: {len(message['tool_calls'])}")
                
                # Append assistant's tool call message to history
                messages.append(message)
                
                from assistant.skills_registry import registry
                
                # Execute tools
                for tool in message["tool_calls"]:
                    fn_name = tool["function"]["name"]
                    args = tool["function"]["arguments"]
                    print(f"   🔨 Executing {fn_name}({args})")
                    
                    instance = registry.create_instance(fn_name)
                    if instance:
                         context = {} # Can inject context here if needed
                         result = await instance.handle_tool_call(args, context=context)
                    else:
                         result = f"Error: Skill {fn_name} not found."
                    
                    # Add result to messages
                    messages.append({
                        "role": "tool",
                        "content": str(result),
                    })

                # 3. Final Response with Tool Outputs
                final_response = await asyncio.to_thread(
                    ollama.chat,
                    model=self._ollama_model_name,
                    messages=messages
                )
                return final_response["message"]["content"]

            return message["content"]
        except Exception as e:
            print(f"   [!] Ollama: {e}")
            self._ollama_available = False
            return None

    async def _chat_groq(self, user_message: str, history: List[Dict[str, str]]) -> Optional[str]:
        if not self._groq_client:
            return None
        try:
            messages = self._build_messages(user_message, history)
            completion = await asyncio.to_thread(
                self._groq_client.chat.completions.create,
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"   [!] Groq: {e}")
            return None

    async def _chat_nvidia(self, user_message: str, history: List[Dict[str, str]]) -> Optional[str]:
        if not self._nvidia_client:
            return None
        try:
            messages = self._build_messages(user_message, history)
            completion = await asyncio.to_thread(
                self._nvidia_client.chat.completions.create,
                model=NVIDIA_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=1024
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"   [!] Nvidia: {e}")
            return None

    async def _chat_openrouter(self, user_message: str, history: List[Dict[str, str]]) -> Optional[str]:
        if not self._openrouter_client:
            return None
        try:
            messages = self._build_messages(user_message, history)
            completion = await asyncio.to_thread(
                self._openrouter_client.chat.completions.create,
                model=OPENROUTER_MODEL,
                messages=messages,
                extra_headers={"HTTP-Referer": "https://github.com/buddy-assistant"},
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"   [!] OpenRouter: {e}")
            return None

    async def _chat_gemini(self, user_message: str, history: List[Dict[str, str]]) -> Optional[str]:
        if not self._gemini_client:
            return None
        try:
            # Reconstruct history from argument
            history_text = ""
            if history:
                history_text = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history])
            
            # Build memory prompt (same logic as _build_messages)
            memory_prompt = ""
            if self.long_term_memory:
                try:
                    relevant_memories = self.long_term_memory.search(
                        query=user_message,
                        limit=5,
                        min_confidence=0.7
                    )
                    if relevant_memories:
                        memory_lines = [f"- {m.content}" for m in relevant_memories]
                        memory_prompt = "\n\nRELEVANT MEMORIES:\n" + "\n".join(memory_lines)
                except Exception:
                    pass

            full_prompt = f"{SYSTEM_PROMPT}{memory_prompt}\n\nPrevious conversation:\n{history_text}\n\nUser: {user_message}\nAssistant:"
            
            response = await asyncio.to_thread(
                self._gemini_client.models.generate_content,
                model=GEMINI_MODEL,
                contents=full_prompt
            )
            return response.text
        except Exception as e:
            print(f"   [!] Gemini: {e}")
            return None

    def clear_history(self):
        """Deprecated: Logic logic removed. Handled by Main."""
        pass

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics for debugging/monitoring"""
        stats = {}
        if self.long_term_memory:
            ltm_stats = self.long_term_memory.get_stats()
            stats["long_term"] = ltm_stats
        return stats

