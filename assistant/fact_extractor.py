"""
Fact Extractor - Extracts personal information from conversations using LLM

Integrates with LongTermMemory for persistent, searchable user facts.
"""

import json

DISTILLATION_PROMPT = """Analyze the following conversation exchange and extract any new permanent facts and entity relationships about the user.

Categories for facts:
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
3. If no new facts or relationships are found, return empty lists.
4. Output MUST be valid JSON with "facts" and "relationships" keys.
5. Confidence should be 0.0-1.0 based on how clearly the fact was stated.
6. Relationships should capture connections between named entities using subject-predicate-object triples.

Example output:
{{
  "facts": [
    {{"category": "preference", "content": "User prefers dark mode in their IDE", "confidence": 0.9}},
    {{"category": "habit", "content": "User usually wakes up at 7am", "confidence": 0.8}}
  ],
  "relationships": [
    {{"subject": "User", "predicate": "works_at", "object": "Microsoft", "confidence": 0.95}},
    {{"subject": "Sarah", "predicate": "is_wife_of", "object": "User", "confidence": 1.0}},
    {{"subject": "User", "predicate": "has_dog_named", "object": "Max", "confidence": 0.9}}
  ]
}}

Conversation to analyze:
User: {user_msg}
Assistant: {assistant_msg}

Extracted Facts and Relationships (JSON):"""


class FactExtractor:
    _SKIP_PATTERNS = {
        "hello",
        "hi",
        "hey",
        "thanks",
        "thank you",
        "ok",
        "okay",
        "good",
        "good morning",
        "good night",
        "bye",
        "goodbye",
        "yes",
        "no",
        "yep",
        "nope",
        "sure",
        "alright",
        "great",
        "nice",
        "cool",
        "awesome",
        "got it",
        "i see",
        "understood",
        "right",
        "correct",
        "yeah",
        "nah",
        "morning",
        "evening",
        "good afternoon",
        "how are you",
        "what's up",
        "welcome",
        "no problem",
        "my pleasure",
        "anytime",
    }

    def __init__(self, llm_router, conversation_memory=None, long_term_memory=None):
        self.llm_router = llm_router
        self.memory = conversation_memory
        self.ltm = long_term_memory  # LongTermMemory instance

    def _should_skip_extraction(self, user_msg: str, assistant_msg: str) -> bool:
        if len(user_msg.strip()) < 5:
            return True
        combined = (user_msg + " " + assistant_msg).strip()
        if len(combined) < 15:
            return True
        lower = user_msg.lower().strip().rstrip("!?.,")
        if lower in self._SKIP_PATTERNS:
            return True
        if lower.split()[0] in {"thanks", "thank", "thx"}:
            return True
        return False

    async def extract_facts_async(self, user_msg: str, assistant_msg: str):
        """Run extraction in the background and store facts + relationships in LongTermMemory"""
        try:
            if self._should_skip_extraction(user_msg, assistant_msg):
                return

            prompt = DISTILLATION_PROMPT.format(
                user_msg=user_msg, assistant_msg=assistant_msg
            )
            raw_response = self._get_fast_completion(prompt)

            if not raw_response:
                return

            try:
                json_str = raw_response.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()

                parsed = json.loads(json_str)

                # Handle both old format (list) and new format (dict with facts/relationships)
                facts = []
                relationships = []
                if isinstance(parsed, list):
                    facts = parsed
                elif isinstance(parsed, dict):
                    facts = parsed.get("facts", [])
                    relationships = parsed.get("relationships", [])

                # Process facts
                for fact in facts:
                    category = fact.get("category", "general")
                    content = fact.get("content")
                    confidence = fact.get("confidence", 0.8)

                    if content and confidence >= 0.7:
                        print(
                            f"   [BRAIN] Fact: [{category}] {content} ({confidence:.2f})"
                        )

                        msg_id = self.memory.add("system", f"FACT: {content}")
                        self.memory.add_fact(content, category, msg_id)

                        if self.ltm:
                            self.ltm.store(
                                content=content,
                                category=category,
                                confidence=confidence,
                                source="extraction",
                            )

                # Process relationships (Knowledge Graph)
                for rel in relationships:
                    subject = rel.get("subject")
                    predicate = rel.get("predicate")
                    obj = rel.get("object")
                    confidence = rel.get("confidence", 0.8)

                    if subject and predicate and obj and confidence >= 0.7:
                        print(
                            f"   [GRAPH] Relationship: {subject} —{predicate}→ {obj} ({confidence:.2f})"
                        )

                        if self.ltm and hasattr(self.ltm, "store_relationship"):
                            self.ltm.store_relationship(
                                subject=subject,
                                predicate=predicate,
                                obj=obj,
                                confidence=confidence,
                            )

            except json.JSONDecodeError:
                pass

        except Exception as e:
            print(f"   [!] Fact extraction error: {e}")

    def _get_fast_completion(self, prompt: str) -> str | None:
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
                    messages=[{"role": "user", "content": prompt}],
                )
                return response["message"]["content"]
            except Exception:
                pass

        return None
