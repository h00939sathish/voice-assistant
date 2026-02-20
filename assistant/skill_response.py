"""
Skill Response - Structured response type for conversation control
"""
from dataclasses import dataclass


@dataclass
class SkillResponse:
    """
    Structured skill response with conversation flow control.
    
    Allows skills to signal whether the assistant should continue
    listening for follow-up commands without requiring the wake word.
    """
    text: str                           # Response text to speak
    continue_listening: bool = False    # If True, skip wake word after speaking
    timeout: float = 10.0               # How long to listen for follow-up (seconds)
    
    def __str__(self) -> str:
        """Allow using SkillResponse as a string for backward compatibility"""
        return self.text
    
    @classmethod
    def simple(cls, text: str) -> 'SkillResponse':
        """Create a simple response that returns to idle"""
        return cls(text=text, continue_listening=False)
    
    @classmethod
    def with_followup(cls, text: str, timeout: float = 10.0) -> 'SkillResponse':
        """Create a response that expects follow-up input"""
        return cls(text=text, continue_listening=True, timeout=timeout)
