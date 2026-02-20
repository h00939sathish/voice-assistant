"""
Unit tests for the DI Container system.
"""
import pytest
from assistant.di import Container
from assistant.interfaces import IAudioManager, ILLMProvider


class SimpleMockAudio(IAudioManager):
    def start_stream(self): pass
    def stop_stream(self): pass
    def get_audio_chunk(self): return b""
    def play_file(self, p): pass


def test_container_singleton_registration():
    """Verify that singleton registration works correctly"""
    Container.clear()
    mock_instance = SimpleMockAudio()
    
    Container.register(IAudioManager, mock_instance)
    resolved = Container.resolve(IAudioManager)
    
    assert resolved is mock_instance
    assert isinstance(resolved, IAudioManager)


def test_container_type_registration():
    """Verify that type registration creates a singleton instance on first resolve"""
    Container.clear()
    Container.register(IAudioManager, SimpleMockAudio)
    
    resolved1 = Container.resolve(IAudioManager)
    resolved2 = Container.resolve(IAudioManager)
    
    assert isinstance(resolved1, SimpleMockAudio)
    assert resolved1 is resolved2


def test_container_factory_registration():
    """Verify that factory registration creates a new instance every time"""
    Container.clear()
    Container.register(IAudioManager, SimpleMockAudio, is_singleton=False)
    
    resolved1 = Container.resolve(IAudioManager)
    resolved2 = Container.resolve(IAudioManager)
    
    assert resolved1 is not resolved2
    assert isinstance(resolved1, SimpleMockAudio)


def test_container_unregistered_resolve():
    """Verify that resolving an unregistered interface raises ValueError"""
    Container.clear()
    with pytest.raises(ValueError, match="No implementation registered"):
        Container.resolve(ILLMProvider)
