"""
Text-to-Speech with edge-tts and pyttsx3 fallback
"""

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import AsyncGenerator

import aiohttp
import edge_tts
import pyttsx3

logger = logging.getLogger("buddy.tts")

from assistant.interfaces import ITTSProvider

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    ELEVENLABS_API_KEY,
    TTS_OFFLINE_VOICE,
    TTS_PITCH,
    TTS_RATE,
    TTS_USE_OFFLINE,
    TTS_VOICE,
)


class TextToSpeech(ITTSProvider):
    """TTS with ElevenLabs (primary), edge-tts (secondary), and pyttsx3 (offline fallback)"""

    # Common phrases to pre-cache
    CACHE_PHRASES = [
        "Good morning!",
        "Sure!",
        "Okay.",
        "I'm sorry, I didn't understand that.",
        "Is there anything else I can help you with?",
    ]

    def __init__(self):
        self.voice = TTS_VOICE
        self.rate = TTS_RATE
        self.pitch = TTS_PITCH
        self._pyttsx_engine: pyttsx3.Engine | None = None
        self._use_fallback = False
        self._cache: dict[str, bytes] = {}  # Text -> MP3 cache
        self._cache_dir = os.path.join(tempfile.gettempdir(), "buddy_tts_cache")
        self._stop_event = asyncio.Event()
        self._player_process = None
        self.elevenlabs_voice_id = "pNInz6obpgDQGcFmaJgB"  # Adam (Default)
        os.makedirs(self._cache_dir, exist_ok=True)

    def _init_fallback(self):
        """Initialize pyttsx3 fallback engine"""
        if self._pyttsx_engine is None:
            self._pyttsx_engine = pyttsx3.init()
            # Configure voice properties
            self._pyttsx_engine.setProperty("rate", 175)  # Words per minute
            voices = self._pyttsx_engine.getProperty("voices")
            # Try to find a female voice for consistency
            for voice in voices:
                if "female" in voice.name.lower() or "zira" in voice.name.lower():
                    self._pyttsx_engine.setProperty("voice", voice.id)
                    break
            logger.info("   ✅ Fallback TTS (pyttsx3) initialized")

    def _emit_health(self, state: str, detail: str = "") -> None:
        """Publish TTS subsystem health (best-effort)."""
        try:
            from assistant.events import SubsystemStateEvent, bus

            bus.publish(
                SubsystemStateEvent(subsystem="tts", state=state, detail=detail)
            )
        except Exception:
            pass

    async def _synthesize_elevenlabs(self, text: str) -> bytes | None:
        """Synthesize via ElevenLabs directly returning the full audio bytes."""
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.elevenlabs_voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY,
        }
        data = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        self._emit_health("healthy")
                        return await response.read()
                    print(
                        f"   ⚠️ ElevenLabs API Error {response.status}: {await response.text()}"
                    )
        except Exception as e:
            print(f"   ⚠️ ElevenLabs network error: {e}")
        return None

    async def _synthesize_elevenlabs_streaming(
        self, text: str
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize via ElevenLabs via streaming HTTP endpoint."""
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.elevenlabs_voice_id}/stream?output_format=mp3_44100_128"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY,
        }
        data = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        # Yield raw chunks as they download
                        async for chunk in response.content.iter_chunked(4096):
                            yield chunk
                    else:
                        error_msg = await response.text()
                        print(
                            f"   ⚠️ ElevenLabs API Error {response.status}: {error_msg}"
                        )
                        raise Exception(f"HTTP {response.status}: {error_msg}")
        except Exception as e:
            print(f"   ⚠️ ElevenLabs streaming error: {e}")
            raise e

    async def synthesize(self, text: str) -> bytes | None:
        """
        Synthesize text to audio. Uses edge-tts directly (skip ElevenLabs).
        """
        use_elevenlabs = os.getenv("USE_ELEVENLABS_TTS", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if use_elevenlabs and ELEVENLABS_API_KEY:
            audio = await self._synthesize_elevenlabs(text)
            if audio:
                return audio

        try:
            communicate = edge_tts.Communicate(
                text, voice=self.voice, rate=self.rate, pitch=self.pitch
            )

            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]

            if audio_data:
                return audio_data

        except Exception as e:
            logger.warning(f"   ⚠️ edge-tts failed: {e}, trying offline...")
            self._use_fallback = True
            self._emit_health("degraded", "edge-tts failed")

        # Try offline TTS (Piper) if enabled
        if TTS_USE_OFFLINE:
            try:
                audio_data = await self._synthesize_offline(text)
                if audio_data:
                    logger.info("   🔊 Using offline TTS (Piper)")
                    return audio_data
            except Exception as e2:
                logger.warning(f"   ⚠️ offline TTS failed: {e2}, using pyttsx3...")

        # Final fallback to pyttsx3
        self._use_fallback = True
        return None

    async def _synthesize_offline(self, text: str) -> bytes | None:
        """Synthesize using Piper TTS (offline)"""
        try:
            import subprocess
            import tempfile

            import piper
        except ImportError:
            logger.warning("piper not installed")
            return None

        voice_path = os.getenv("PIPER_VOICE_PATH", "")
        if not voice_path or not os.path.exists(voice_path):
            vo = TTS_OFFLINE_VOICE
            logger.warning(
                f"Piper voice not configured: {vo}. Set PIPER_VOICE_PATH in .env"
            )
            return None

        config_path = voice_path.replace(".onnx", ".onnx.json")
        if not os.path.exists(config_path):
            logger.warning(f"Piper config not found: {config_path}")
            return None

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                out_wav = f.name

            subprocess.run(
                [
                    "python",
                    "-m",
                    piper.__name__,
                    "-m",
                    voice_path,
                    "-c",
                    config_path,
                    "-i",
                    "-",
                    "-f",
                    out_wav,
                ],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )

            if os.path.exists(out_wav):
                with open(out_wav, "rb") as f:
                    wav_data = f.read()
                os.unlink(out_wav)
                return wav_data

        except Exception as e:
            logger.warning(f"Piper TTS failed: {e}")
        return None

    async def synthesize_streaming(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Stream audio chunks as they're generated. Uses edge-tts directly (skip ElevenLabs).
        """
        use_elevenlabs = os.getenv("USE_ELEVENLABS_TTS", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if use_elevenlabs and ELEVENLABS_API_KEY:
            # Check if ElevenLabs works and yields at least one chunk
            success = False
            try:
                async for chunk in self._synthesize_elevenlabs_streaming(text):
                    success = True
                    yield chunk
            except Exception as e:
                print(f"   ⚠️ Falling back to Edge-TTS after ElevenLabs exception: {e}")

            if success:
                return

        # Use Edge-TTS
        try:
            communicate = edge_tts.Communicate(
                text, voice=self.voice, rate=self.rate, pitch=self.pitch
            )

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        except Exception as e:
            print(f"   ⚠️ edge-tts streaming failed: {e}")
            self._use_fallback = True
            self._emit_health("degraded", "edge-tts failed")

    def speak(self, text: str):
        """
        Speak text - tries cache, then online TTS, falls back to pyttsx3.
        Safe to call from both sync and async contexts.
        """
        if text in self._cache:
            self._play_mp3(self._cache[text])
            return

        if self._use_fallback:
            self._speak_fallback(text)
            return

        try:
            # If called from a running event loop, schedule on it instead of asyncio.run()
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(self.synthesize(text), loop)
            audio_data = future.result(timeout=30.0)
        except RuntimeError:
            # No running loop — safe to create one
            try:
                audio_data = asyncio.run(self.synthesize(text))
            except Exception as e:
                print(f"   ⚠️ TTS error: {e}, using fallback")
                self._speak_fallback(text)
                return

        if audio_data:
            self._cache[text] = audio_data
            self._play_mp3(audio_data)
        else:
            self._speak_fallback(text)

    def _speak_fallback(self, text: str):
        """Speak using pyttsx3 (offline)"""
        try:
            self._init_fallback()
            if self._pyttsx_engine is None:
                logger.error("pyttsx3 engine unavailable, cannot speak")
                return
            logger.info("   🔊 Using offline TTS...")
            self._pyttsx_engine.say(text)
            self._pyttsx_engine.runAndWait()
        except Exception as e:
            logger.error(f"   ❌ Fallback TTS failed: {e}")

    def _play_mp3(self, mp3_data: bytes):
        """Play MP3 audio data"""
        try:
            # Save to temp file and play
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(mp3_data)
                temp_path = f.name

            # Use ffmpeg/pydub if available, otherwise sounddevice
            try:
                from pydub import AudioSegment
                from pydub.playback import play

                audio = AudioSegment.from_mp3(temp_path)
                play(audio)
                # pydub blocks until done, safe to delete
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            except ImportError:
                # Fallback: use system player
                if sys.platform == "win32":
                    os.startfile(temp_path)
                    # os.startfile is async on Windows — delay cleanup
                    import threading

                    def _delayed_cleanup(path, delay=10):
                        import time

                        time.sleep(delay)
                        try:
                            os.unlink(path)
                        except OSError:
                            pass

                    threading.Thread(
                        target=_delayed_cleanup, args=(temp_path,), daemon=True
                    ).start()
                else:
                    subprocess.run(["mpv", "--no-video", temp_path], check=False)
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass

        except Exception as e:
            print(f"   ⚠️ Audio playback error: {e}")

    async def speak_streaming(self, text: str):
        """
        Speak with streaming - starts playback immediately as audio is generated.
        Pipes audio data directly to a media player process (mpv).
        """
        self._stop_event.clear()
        self._player_process = None

        try:
            # Check for mpv or ffplay
            player = shutil.which("mpv")
            args = ["mpv", "--no-video", "--no-terminal", "-"]

            if not player:
                player = shutil.which("ffplay")
                args = ["ffplay", "-nodisp", "-autoexit", "-"]

            if not player:
                logger.warning("   ⚠️ No streaming player (mpv/ffplay) found, buffering...")
                # Fallback to buffering
                audio_chunks = []
                async for chunk in self.synthesize_streaming(text):
                    if self._stop_event.is_set():
                        break
                    audio_chunks.append(chunk)
                if audio_chunks and not self._stop_event.is_set():
                    self._play_mp3(b"".join(audio_chunks))
                return

            # Start player process reading from stdin
            self._player_process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )

            # Pipe chunks to player
            try:
                async for chunk in self.synthesize_streaming(text):
                    if self._stop_event.is_set():
                        logger.info("   🛑 TTS streaming interrupted!")
                        break
                    if chunk and self._player_process.poll() is None:
                        self._player_process.stdin.write(chunk)
                        self._player_process.stdin.flush()
            except BrokenPipeError:
                pass  # Player closed
            finally:
                if self._player_process and self._player_process.poll() is None:
                    if self._player_process.stdin:
                        self._player_process.stdin.close()
                    # Wait briefly, kill if stuck
                    try:
                        self._player_process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        self._player_process.kill()
                self._player_process = None

        except Exception as e:
            if not self._stop_event.is_set():
                print(f"   ⚠️ Streaming TTS error: {e}, switching to offline voice")
                self._use_fallback = True
                self._speak_fallback(text)

    def stop(self):
        """Stop any ongoing speech mid-sentence."""
        self._stop_event.set()
        if hasattr(self, "_player_process") and self._player_process:
            try:
                self._player_process.kill()
            except Exception as e:
                logger.debug(f"Failed to kill TTS player process: {e}")
            self._player_process = None

        # Also clean up standard mp3 playback if we're using a cached response
        if sys.platform != "win32":
            # For non-windows we spawn `mpv` inside `_play_mp3`, we could kill it
            # but Windows uses os.startfile which we can't easily kill without process hunting.
            pass


def test_tts():
    """Test TTS"""
    tts = TextToSpeech()

    logger.info("\n🔊 Testing edge-tts (online)...")
    tts.speak(
        "Hello! I'm Buddy, your friendly voice assistant. How can I help you today?"
    )

    logger.info("\n🔊 Testing fallback (offline)...")
    tts._use_fallback = True
    tts.speak("This is the offline fallback voice.")

    logger.info("\n✅ TTS test complete!")


if __name__ == "__main__":
    test_tts()
