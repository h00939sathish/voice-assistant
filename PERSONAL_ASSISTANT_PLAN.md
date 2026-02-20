# Personal Voice Assistant - Enhancement Plan

**Goal:** Transform Buddy into *your* personal assistant with distinct personality, long-term memory, and powerful laptop control.

**Scope:** Personal use, local-first, privacy-focused, no enterprise complexity.

---

## Core Philosophy

- **Local-first:** Works offline, your data stays on your machine
- **Personal:** Remembers your preferences, habits, context
- **Capable:** Can actually *do* things on your laptop
- **Character:** Has personality, not just a robot

---

## Phase 1: Long-Term Memory System (Week 1-2)

### Current State
Basic conversation memory (last 10 messages), no persistence between sessions.

### Target State
Assistant remembers facts, preferences, and context forever.

### Implementation

**Week 1: Fact Extraction & Storage**
```python
# Memory types to implement:
- Personal facts ("I work at Microsoft", "My wife's name is Sarah")
- Preferences ("I like jazz music", "Prefer Celsius")
- Habits ("Usually wake up at 7am", "Check email first thing")
- Context ("Working on Python project", "Planning trip to Japan")
- Relationships ("Boss is John", "Dog is named Max")
```

Files to modify:
- `assistant/fact_extractor.py` - Improve extraction
- `assistant/conversation_memory.py` - Add vector storage
- New: `assistant/long_term_memory.py` - Persistent memory with search

**Week 2: Memory Retrieval**
- Semantic search through memories (not just keyword)
- Contextual recall (relevant facts based on current conversation)
- Memory confidence scoring
- User correction ("That's not right, I meant...")

**Deliverables:**
- SQLite + local vector DB (sqlite-vec or chromadb)
- Memories persist between sessions
- Natural recall ("What's my wife's name?" → "Sarah")

---

## Phase 2: Personality & Character (Week 3)

### Current State
Basic system prompt, robotic responses.

### Target State
Distinct personality with consistent character traits.

### Implementation

**Personality Configuration**
```python
# config.py additions
PERSONALITY_TYPE = "witty_assistant"  # Options: professional, friendly, witty, concise
VOICE_TONE = "casual"
USE_EMOJI = True
JOKES_ALLOWED = True
MEMORY_REFERENCING = True  # "Like you mentioned yesterday..."
```

**Character Definition**
Edit `assistant/personality.py`:
- Name: Buddy (or change to whatever you prefer)
- Speaking style: Casual, occasional humor, helpful but not obsequious
- Memory usage: References past conversations naturally
- Initiative: Occasionally suggests things based on context

**Dynamic Personality**
- Adapts tone based on your mood (detected from speech patterns)
- Professional for work tasks, casual for chat
- Can be snarky if you enable it

**Deliverables:**
- Updated personality.py with character definition
- Personality profiles in `config/personalities/`
- Mood detection based on command patterns

---

## Phase 3: Laptop Control Tools (Week 4-5)

### Current State
MCP skill exists but basic. Limited laptop control.

### Target State
Can control most aspects of your laptop through voice.

### Implementation

**Week 4: Desktop Commander Integration**
Ensure these work reliably:
```
"Open Chrome and go to Gmail"
"Find files I edited yesterday"
"Take a screenshot and save it"
"Check disk space"
"List running processes"
"Kill process [name]"
"Open VS Code with my project"
"Empty recycle bin"
"Create folder [name] on desktop"
```

Files to modify:
- `skills/mcp_skill.py` - Better tool selection
- `assistant/app_controller.py` - Expand app control

**Week 5: Custom Laptop Tools**
Create specialized tools:

1. **File Manager**
   ```python
   # skills/file_manager_skill.py
   - "Find my resume PDF"
   - "Move downloaded images to Photos folder"
   - "Open my latest download"
   - "What's in my Downloads?"
   ```

2. **System Monitor**
   ```python
   # skills/system_monitor_skill.py
   - "How's my CPU usage?"
   - "What's using the most memory?"
   - "Check my battery"
   - "Is my internet working?"
   ```

3. **Window Manager**
   ```python
   # skills/window_manager_skill.py
   - "Close all windows"
   - "Minimize everything"
   - "Switch to VS Code"
   - "Arrange windows side by side"
   - "Maximize this window"
   ```

4. **Quick Actions**
   ```python
   # skills/quick_actions_skill.py
   - "Lock my computer"
   - "Put it to sleep"
   - "Restart"
   - "Shut down in 10 minutes"
   - "Mute volume"
   - "Set brightness to 50%"
   ```

**Deliverables:**
- 4 new skills for laptop control
- Reliable MCP integration
- Natural language command parsing

---

## Phase 4: Proactive Assistant (Week 6)

### Current State
Reactive - only responds when spoken to.

### Target State
Proactive - can initiate based on triggers.

### Implementation

**Proactive Triggers**
```python
# assistant/proactive_engine.py

Time-based:
- "Good morning" at 8am (if not greeted)
- "Don't forget your meeting at 2pm" (15 min before)
- "Time to take a break" (after 2 hours work)

Context-based:
- "I see you're coding, want music?" (detect IDE focus)
- "Your CPU is at 90%, something's running hard"
- "Battery at 20%, plug in soon"

Habit-based:
- "Usually check email now, want me to open it?"
- "It's your lunch time"
```

**Smart Suggestions**
- Remember your patterns
- Suggest actions based on context
- "You always open Spotify when working, want me to?"

**Deliverables:**
- `assistant/proactive_engine.py`
- Configurable proactive behaviors
- Focus detection (what app you're in)

---

## Phase 5: Smart Context Awareness (Week 7)

### Current State
Each command is isolated.

### Target State
Understands what you're doing and responds accordingly.

### Implementation

**Activity Detection**
```python
# assistant/context_engine.py

def detect_activity():
    - Active window/app
    - Recent files opened
    - Time of day
    - Day of week
    - Previous commands context
```

**Contextual Responses**
```
You: "Save it"
Assistant: "Save the document you're working on?" (knows you have Word open)

You: "Play something"
Assistant: "Playing your coding playlist" (knows you were coding)

You: "Remind me tomorrow"
Assistant: "Remind you about the email to John about the project?"
```

**Session Memory**
- Current task context
- Recent actions
- Pending/incomplete requests

**Deliverables:**
- `assistant/context_engine.py`
- Activity detection
- Contextual command interpretation

---

## Phase 6: Voice & Interaction Polish (Week 8)

### Current State
Basic TTS, no voice customization.

### Target State
Natural, pleasant voice interaction.

### Implementation

**Voice Improvements**
- Better TTS voice selection (Edge TTS has good options)
- Interruptible speech ("Stop" while speaking)
- Confirmation sounds (gentle beeps, not jarring)
- Whisper mode (quiet responses at night)

**Conversation Flow**
- Natural follow-ups ("What else?" "Anything else I can do?")
- Clarification when unsure ("Did you mean...?")
- Graceful "I don't know" with offer to search

**Wake Word Alternatives**
- "Hey Buddy" (custom wake word)
- Visual trigger (orb glows when listening)
- Hotkey always works

**Deliverables:**
- Updated TTS with better voices
- Interrupt handling
- Conversation flow improvements

---

## Quick Wins (Do These First)

### 1. Fix Memory Now (1 day)
```python
# In config.py
ENABLE_LONG_MEMORY = True
MEMORY_DB_PATH = "data/memory.db"

# In main.py
from assistant.long_term_memory import LongTermMemory
self.long_memory = LongTermMemory()
```

### 2. Improve Personality (2 hours)
Edit `assistant/personality.py`:
```python
SYSTEM_PROMPT = """You are Buddy, a personal assistant with personality.

Traits:
- Helpful but not overly formal
- Remember details about the user
- Occasional light humor
- Proactive suggestions when appropriate
- Uses context from previous conversations

When you know facts about the user, reference them naturally.
"""
```

### 3. Better MCP Integration (1 day)
Improve `skills/mcp_skill.py`:
- Better tool selection logic
- Error handling
- Confirmation for destructive actions

---

## File Structure After Changes

```
assistant/
├── personality.py          # Character definition
├── conversation_memory.py  # Short-term memory
├── long_term_memory.py     # NEW: Persistent memory
├── fact_extractor.py       # Improved: Extract facts from conversations
├── context_engine.py       # NEW: Activity detection
├── proactive_engine.py     # NEW: Proactive behaviors
├── mcp_client.py           # NEW: Better MCP wrapper

skills/
├── mcp_skill.py            # Improved: Laptop control
├── file_manager_skill.py   # NEW: File operations
├── system_monitor_skill.py # NEW: System stats
├── window_manager_skill.py # NEW: Window control
├── quick_actions_skill.py  # NEW: System actions
└── ...existing skills

data/
├── memory.db               # Long-term memory
├── facts.json              # Extracted facts
└── context.json            # Session context
```

---

## Personalization Checklist

Make it truly yours:

- [ ] Choose assistant name (Buddy, Jarvis, Friday, etc.)
- [ ] Set personality type (professional, casual, witty)
- [ ] Configure proactive behaviors you want
- [ ] Set up personal facts (work, family, preferences)
- [ ] Choose preferred apps for common tasks
- [ ] Set daily/weekly routines
- [ ] Configure voice preferences
- [ ] Set privacy boundaries (what it can/cannot access)

---

## Success Metrics

You'll know it's working when:

1. **Memory:** It remembers your wife's name, where you work, what you like
2. **Personality:** Responses feel natural, not robotic
3. **Control:** Can reliably open apps, manage files, control system
4. **Context:** "Save it" works without specifying what
5. **Proactive:** Occasionally helpful unprompted suggestions

---

## Minimal Viable Personal Assistant (1 Week)

If you want just the essentials:

**Day 1:** Fix long-term memory (sqlite-based)
**Day 2:** Improve personality prompt
**Day 3:** Ensure MCP/Desktop Commander works well
**Day 4:** Add file manager skill
**Day 5:** Add quick actions skill
**Day 6:** Polish conversation flow
**Day 7:** Test everything together

This gives you 80% of the value in 1 week.

---

## Tools You'll Need

New dependencies (minimal):
```
sqlite-vec          # Vector search for memory
psutil              # System monitoring (already have)
pywin32             # Windows control (already have)
pyautogui           # GUI automation
```

All local, no cloud APIs required except for LLM (which can be local Ollama).

---

*This is YOUR assistant. Customize it however you want.*
