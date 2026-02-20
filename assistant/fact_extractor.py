"""
Fact Extractor - Extracts personal information from conversations using LLM

Integrates with LongTermMemory for persistent, searchable user facts.
"""
import json
from typing import Optional

DISTILLATION_PROMPT = """Analyze the following conversation exchange and extract any new permanent facts about the user.

Categories:
- personal: Name, age, location, work, education ("I work at Microsoft", "I'm 30 years old")
- preference: Likes, dislikes, choices ("I prefer dark mode", "I hate cilantro")
- habit: Regular behaviors, routines ("I wake up at 7am", "I check email first")
- relationship: People, pets, connections ("My wife is Sarah", "My boss is John")
- context: Current activities, projects ("Working on a Python project", "Planning Japan trip")
- goal: Plans, aspirations ("Want to learn Spanish", "Planning to buy a house")
- event: Important past events ("Got married last year", "Moved to Seattle")

Rules:
1. ONLY extract permanent or long-term facts. (e.g., "User likes coffee" is a fact, "User is hungry right now" is NOT).
2. Be SPECIFIC and CONCISE. Extract the exact fact, not generalizations.
3. If no new facts are found, return an empty list [].
4. Output MUST be a valid JSON list of objects with "category", "content", and "confidence" fields.
5. Confidence should be 0.0-1.0 based on how clearly the fact was stated.

Example output:
[
  {{"category": "preference", "content": "User prefers dark mode in their IDE", "confidence": 0.9}},
  {{"category": "relationship", "content": "User has a wife named Sarah", "confidence": 1.0}},
  {{"category": "habit", "content": "User usually wakes up at 7am", "confidence": 0.8}}
]

Conversation to analyze:
User: {user_msg}
Assistant: {assistant_msg}

Extracted Facts (JSON):"""

class FactExtractor:
    def __init__(self, llm_router, conversation_memory=None, long_term_memory=None):
        self.llm_router = llm_router
        self.memory = conversation_memory
        self.ltm = long_term_memory  # LongTermMemory instance

    async def extract_facts_async(self, user_msg: str, assistant_msg: str):
        """Run extraction in the background and store in LongTermMemory"""
        try:
            # Skip extraction for very short messages
            if len(user_msg) < 5:
                return

            prompt = DISTILLATION_PROMPT.format(user_msg=user_msg, assistant_msg=assistant_msg)
            raw_response = self._get_fast_completion(prompt)

            if not raw_response:
                return

            # Parse JSON
            try:
                # Clean response (sometimes LLMs wrap in markdown code blocks)
                json_str = raw_response.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()

                facts = json.loads(json_str)
                if isinstance(facts, list):
                    for fact in facts:
                        category = fact.get("category", "general")
                        content = fact.get("content")
                        confidence = fact.get("confidence", 0.8)

                        if content and confidence >= 0.7:  # Only store high-confidence facts
                            print(f"   [BRAIN] Fact Extracted: [{category}] {content} (confidence: {confidence:.2f})")

                            # Store in both conversation memory (legacy) and long-term memory
                            msg_id = self.memory.add("system", f"FACT: {content}")
                            self.memory.add_fact(content, category, msg_id)

                            # Store in LongTermMemory if available (with semantic search)
                            if self.ltm:
                                self.ltm.store(
                                    content=content,
                                    category=category,
                                    confidence=confidence,
                                    source="extraction"
                                )
            except json.JSONDecodeError:
                pass

        except Exception as e:
            print(f"   [!] Fact extraction error: {e}")

    def _get_fast_completion(self, prompt: str) -> Optional[str]:
        """Internal helper to get a fast completion for distillation"""
        # We try Groq first for speed, then Ollama
        if self.llm_router._groq_client:
            try:
                completion = self.llm_router._groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=512,
                )
                return completion.choices[0].message.content
            except Exception:
                pass
        
        if self.llm_router._check_ollama():
            try:
                import ollama
                response = ollama.chat(
                    model=self.llm_router._ollama_model_name,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response["message"]["content"]
            except Exception:
                pass
                
        return None
