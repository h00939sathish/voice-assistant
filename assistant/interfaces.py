"""
Interfaces - Abstract Base Classes for core assistant components.
Enforces Dependency Injection and swaps providers easily.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union, Generator, AsyncGenerator


class IAudioManager(ABC):
    """Interface for audio input/output management"""
    @abstractmethod
    def start_stream(self): pass
    
    @abstractmethod
    def stop_stream(self): pass
    
    @abstractmethod
    def get_audio_chunk(self) -> bytes: pass
    
    @abstractmethod
    def play_file(self, file_path: str): pass


class ISTTProvider(ABC):
    """Interface for Speech-to-Text providers"""
    @abstractmethod
    def load_models(self): pass
    
    @abstractmethod
    def transcribe(self, audio_data: bytes) -> tuple[str, float]: pass
    
    @abstractmethod
    def listen_with_vad(self, audio_manager: IAudioManager, timeout: float = 15.0) -> Optional[bytes]: pass


class ITTSProvider(ABC):
    """Interface for Text-to-Speech providers"""
    @abstractmethod
    async def speak(self, text: str): pass
    
    @abstractmethod
    async def speak_streaming(self, text: str): pass
    
    @abstractmethod
    def stop(self): pass


class ILLMProvider(ABC):
    """Interface for Large Language Model providers"""
    @abstractmethod
    async def chat(self, user_message: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """Process a message and return a response"""
        pass


class ISkill(ABC):
    """Interface for assistant skills"""
    @abstractmethod
    async def handle(self, text: str, context: Dict[str, Any]) -> Any: pass
    
    @property
    @abstractmethod
    def metadata(self): pass
