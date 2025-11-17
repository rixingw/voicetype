#!/usr/bin/env python3
"""
VoiceType - Voice-to-Text Input Tool
Press-to-talk voice transcription that types directly into your active application.
"""

import whisper
import sounddevice as sd
import soundfile as sf
import argparse
import sys
import numpy as np
from pathlib import Path
import tempfile
import os
import warnings
import threading
import time
import subprocess
import atexit
import signal
from pynput import keyboard
from pynput.keyboard import Controller, Key

# Suppress FP16 warning (harmless - uses FP32 on CPU)
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")

# Lock file for single-instance enforcement
LOCK_FILE = Path.home() / ".voicetype.lock"
_lock_file_handle = None


def _acquire_lock():
    """Acquire a lock file to prevent multiple instances from running."""
    global _lock_file_handle
    
    if LOCK_FILE.exists():
        try:
            with open(LOCK_FILE, 'r') as f:
                pid_str = f.read().strip()
                try:
                    old_pid = int(pid_str)
                    os.kill(old_pid, 0)
                    return False
                except (ValueError, OSError):
                    try:
                        LOCK_FILE.unlink()
                    except Exception:
                        pass
        except Exception:
            try:
                LOCK_FILE.unlink()
            except Exception:
                pass
    
    try:
        _lock_file_handle = open(LOCK_FILE, 'w')
        _lock_file_handle.write(str(os.getpid()))
        _lock_file_handle.flush()
        return True
    except Exception as e:
        print(f"⚠️  Failed to create lock file: {e}")
        return False


def _release_lock():
    """Release the lock file."""
    global _lock_file_handle
    
    if _lock_file_handle:
        try:
            _lock_file_handle.close()
        except Exception:
            pass
        _lock_file_handle = None
    
    if LOCK_FILE.exists():
        try:
            LOCK_FILE.unlink()
        except Exception:
            pass


# Register cleanup on exit
atexit.register(_release_lock)

def _signal_handler(signum, frame):
    _release_lock()
    raise SystemExit(0)

signal.signal(signal.SIGTERM, _signal_handler)


class VoiceType:
    """Voice-to-text input tool with push-to-talk."""
    
    def __init__(self, model_size="base", sample_rate=None, device=None, 
                 save_audio_dir=None, save_transcription_dir=None):
        self.model_size = model_size
        self.sample_rate = sample_rate
        self.device = device
        self.save_audio_dir = Path(save_audio_dir) if save_audio_dir else None
        self.save_transcription_dir = Path(save_transcription_dir) if save_transcription_dir else None
        
        # Recording state
        self.is_recording = False
        self.recording_thread = None
        self.audio_data = None
        self.recording_sample_rate = None
        self.stop_recording_flag = False
        
        # Push-to-talk settings
        self.last_toggle_time = 0.0
        self.toggle_cooldown = 0.3
        self.toggle_in_progress = False
        self.min_record_seconds = 1.2
        self.record_started_at = 0.0
        self.active_key_down_time = 0.0
        self.press_to_talk_key_pressed = False
        self.stop_requested = False
        self.post_roll_seconds = 0.35
        
        # Transcription settings
        self.language_hint = None
        
        # Text delivery settings
        self.send_to_active = None
        self.type_chars_per_sec = 30.0
        self.send_delay = 0.0
        
        # Load Whisper model
        print(f"Loading Whisper model '{model_size}'...")
        self.model = whisper.load_model(model_size)
        print("✅ Model loaded! Ready to record.")
        
        # Create save directories if specified
        if self.save_audio_dir:
            self.save_audio_dir.mkdir(parents=True, exist_ok=True)
        if self.save_transcription_dir:
            self.save_transcription_dir.mkdir(parents=True, exist_ok=True)
    
    def get_macbook_microphone(self):
        """Find and return the MacBook Pro microphone device index."""
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                name = device['name'].lower()
                if 'macbook' in name and 'iphone' not in name:
                    return i, int(device['default_samplerate'])
                if 'macbook pro microphone' in name:
                    return i, int(device['default_samplerate'])
        default_input = sd.default.device[0]
        if default_input is not None:
            default_device = devices[default_input]
            default_name = default_device['name'].lower()
            if 'iphone' not in default_name:
                return default_input, int(default_device['default_samplerate'])
        return None, 16000
    
    def start_recording(self):
        """Start recording audio in a separate thread."""
        if self.is_recording:
            return
        if self.toggle_in_progress:
            return
        self.toggle_in_progress = True
        
        self.is_recording = True
        self.stop_recording_flag = False
        self.record_started_at = time.time()
        
        # Auto-select MacBook microphone if device not specified
        if self.device is None:
            device, device_sample_rate = self.get_macbook_microphone()
            if device is not None:
                if self.sample_rate is None:
                    self.sample_rate = device_sample_rate
                device_info = sd.query_devices(device)
                print(f"\n🎙️  Recording... (Using: {device_info['name']})")
            else:
                if self.sample_rate is None:
                    self.sample_rate = 16000
                print("\n🎙️  Recording... (Using default device)")
                device = sd.default.device[0]
        else:
            if self.sample_rate is None:
                device_info = sd.query_devices(self.device)
                self.sample_rate = int(device_info['default_samplerate'])
            device = self.device
            device_info = sd.query_devices(device)
            print(f"\n🎙️  Recording... (Using: {device_info['name']})")
        
        self.recording_sample_rate = self.sample_rate
        self.stop_requested = False
        
        # Start recording in a separate thread
        self.recording_thread = threading.Thread(
            target=self._record_continuously,
            args=(device,),
            daemon=True
        )
        self.recording_thread.start()
        
        # Start a monitor thread to ensure stop happens when requested
        self.stop_monitor_thread = threading.Thread(
            target=self._monitor_stop_request,
            daemon=True
        )
        self.stop_monitor_thread.start()
        
        self.toggle_in_progress = False
    
    def _monitor_stop_request(self):
        """Background thread that monitors stop_requested and ensures recording stops."""
        while self.is_recording:
            if self.stop_requested:
                elapsed = time.time() - self.record_started_at
                if elapsed >= self.min_record_seconds:
                    self.stop_recording()
                    break
            time.sleep(0.1)
    
    def _record_continuously(self, device):
        """Record audio continuously until stop flag is set."""
        audio_chunks = []
        frames_per_block = int(0.1 * self.sample_rate)
        try:
            with sd.InputStream(samplerate=self.sample_rate,
                                channels=1,
                                device=device,
                                dtype='float32',
                                blocksize=frames_per_block) as stream:
                while not self.stop_recording_flag:
                    block, overflowed = stream.read(frames_per_block)
                    if not self.stop_recording_flag:
                        audio_chunks.append(block[:, 0].copy())
        except Exception as e:
            print(f"\n❌ Error during recording: {e}")
            self.is_recording = False
            return
        if audio_chunks:
            self.audio_data = np.concatenate(audio_chunks)
        else:
            self.audio_data = np.array([], dtype='float32')
    
    def stop_recording(self):
        """Stop recording and transcribe."""
        if not self.is_recording:
            self.stop_requested = False
            return
        if self.toggle_in_progress:
            return
        
        elapsed = time.time() - self.record_started_at
        if elapsed < self.min_record_seconds:
            if self.stop_requested:
                wait_time = self.min_record_seconds - elapsed
                if wait_time > 0:
                    time.sleep(wait_time)
            else:
                self.stop_requested = True
                self.last_toggle_time = time.time()
                return
        
        self.stop_requested = False
        self.toggle_in_progress = True
        
        print("\n⏹️  Stopping recording...")
        time.sleep(self.post_roll_seconds)
        self.stop_recording_flag = True
        self.is_recording = False
        
        if self.recording_thread:
            self.recording_thread.join(timeout=2.0)
        
        if self.audio_data is None or len(self.audio_data) == 0:
            print("⚠️  No audio was recorded!")
            self.toggle_in_progress = False
            return
        
        # Check audio levels
        max_level = np.max(np.abs(self.audio_data))
        rms_level = np.sqrt(np.mean(self.audio_data**2))
        print(f"Audio levels - Peak: {max_level:.4f}, RMS: {rms_level:.4f}")
        
        if max_level < 0.001:
            print("⚠️  WARNING: No audio detected!")
            self.toggle_in_progress = False
            return
        
        # Save audio if requested
        if self.save_audio_dir:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            audio_filename = self.save_audio_dir / f"recording_{timestamp}.wav"
            sf.write(str(audio_filename), self.audio_data, self.recording_sample_rate)
            print(f"💾 Audio saved to '{audio_filename}'")
        
        # Transcribe
        self._transcribe_audio()
        self.toggle_in_progress = False
    
    def _transcribe_audio(self):
        """Transcribe the recorded audio."""
        print("\n📝 Transcribing...")
        
        # Save audio to temporary file for Whisper
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_path = tmp_file.name
            sf.write(tmp_path, self.audio_data, self.recording_sample_rate)
        
        try:
            transcribe_kwargs = {
                "temperature": 0.0,
                "condition_on_previous_text": False,
            }
            if self.language_hint:
                transcribe_kwargs["language"] = self.language_hint
            result = self.model.transcribe(tmp_path, **transcribe_kwargs)
            
            transcription_text = result.get("text", "").strip()
            
            print("\n" + "="*60)
            print("TRANSCRIPTION:")
            print("="*60)
            if transcription_text:
                print(transcription_text)
            else:
                print("(No transcription - audio may be silent or too quiet)")
            print("="*60)
            
            if "language" in result:
                print(f"\n🌐 Detected language: {result['language']}")
            
            # Save transcription if requested
            if self.save_transcription_dir and transcription_text:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                transcription_filename = self.save_transcription_dir / f"transcription_{timestamp}.txt"
                with open(transcription_filename, "w", encoding="utf-8") as f:
                    f.write(transcription_text)
                print(f"💾 Transcription saved to '{transcription_filename}'")
            
            # Send to active app if configured
            if transcription_text and self.send_to_active:
                print("\n⌨️  Sending transcription to active application...")
                self._deliver_transcription(transcription_text)
            
        finally:
            self.last_toggle_time = time.time()
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def _deliver_transcription(self, text: str):
        """Deliver transcription to the currently focused application."""
        try:
            if self.send_delay and self.send_delay > 0:
                time.sleep(self.send_delay)
            
            if self.send_to_active == 'paste':
                # Use pbcopy to set clipboard, then Cmd+V to paste
                try:
                    subprocess.run(["pbcopy"], input=text, text=True, check=True)
                except Exception as e:
                    print(f"⚠️  Clipboard set failed: {e}. Trying AppleScript...")
                    try:
                        as_text = text.replace("\\", "\\\\").replace("\"", "\\\"")
                        script = f'set the clipboard to "{as_text}"'
                        subprocess.run(["osascript", "-e", script], check=True)
                    except Exception as e2:
                        print(f"❌ AppleScript clipboard set failed: {e2}")
                        return
                
                # Try Cmd+V via AppleScript first (more reliable)
                try:
                    script = 'tell application "System Events" to keystroke "v" using command down'
                    subprocess.run(["osascript", "-e", script], check=True, timeout=5)
                    print("✅ Pasted into active app (AppleScript).")
                except Exception as e:
                    print(f"⚠️  AppleScript paste failed: {e}. Trying pynput...")
                    try:
                        kb = Controller()
                        time.sleep(0.1)
                        with kb.pressed(Key.cmd):
                            kb.press('v')
                            kb.release('v')
                        print("✅ Pasted into active app.")
                    except Exception as e2:
                        print(f"❌ Cmd+V paste via pynput also failed: {e2}")
            
            elif self.send_to_active == 'type':
                # Use AppleScript first (more reliable in menu bar apps)
                try:
                    # Escape special characters for AppleScript
                    as_text = text.replace("\\", "\\\\").replace("\"", "\\\"").replace("$", "\\$")
                    script = f'tell application "System Events" to keystroke "{as_text}"'
                    subprocess.run(["osascript", "-e", script], check=True, timeout=30)
                    print("✅ Typed into active app (AppleScript).")
                except Exception as e:
                    print(f"⚠️  AppleScript typing failed: {e}. Trying pynput...")
                    try:
                        kb = Controller()
                        delay = 1.0 / max(self.type_chars_per_sec, 1.0)
                        for ch in text:
                            kb.type(ch)
                            time.sleep(delay)
                        print("✅ Typed into active app.")
                    except Exception as e2:
                        print(f"❌ Typing via pynput also failed: {e2}")
        
        except Exception as e:
            print(f"❌ Failed to send to active app: {e}")
    
    def run_press_to_talk(self, target_key: str):
        """Hold a key to record, release to stop (push-to-talk)."""
        print("\n" + "="*60)
        print("🎯 VOICETYPE - PRESS-TO-TALK READY")
        print("="*60)
        print(f"Hold '{target_key}' to record, release to stop")
        print("Press ESC to quit")
        print("="*60 + "\n")
        self.should_exit = False
        self.press_to_talk_key_pressed = False
        
        def key_matches_target(key_obj, target: str) -> bool:
            """Improved key matching that handles modifier key variants."""
            target = target.lower().strip()
            
            special_map = {
                'space': keyboard.Key.space,
                'enter': keyboard.Key.enter,
                'esc': keyboard.Key.esc,
                'tab': keyboard.Key.tab,
            }
            if target in special_map:
                return key_obj == special_map[target]
            
            modifier_map = {
                'ctrl': keyboard.Key.ctrl,
                'control': keyboard.Key.ctrl,
                'cmd': keyboard.Key.cmd,
                'command': keyboard.Key.cmd,
                'alt': keyboard.Key.alt,
                'option': keyboard.Key.alt,
                'shift': keyboard.Key.shift,
            }
            if target in modifier_map:
                return key_obj == modifier_map[target]
            
            # Regular character key
            try:
                if hasattr(key_obj, 'char') and key_obj.char:
                    return key_obj.char.lower() == target.lower()
                if hasattr(key_obj, 'name'):
                    return key_obj.name.lower() == target.lower()
            except Exception:
                pass
            
            return False
        
        def on_key_press(key):
            try:
                if key_matches_target(key, 'esc'):
                    if self.is_recording:
                        print("\n⚠️  Stopping current recording before exit...")
                        self.stop_recording()
                    print("\n👋 Exiting...")
                    self.should_exit = True
                    return False
                
                if key_matches_target(key, target_key):
                    if self.press_to_talk_key_pressed:
                        return
                    if self.is_recording:
                        return
                    
                    now = time.time()
                    time_since_last = now - self.last_toggle_time
                    if time_since_last < self.toggle_cooldown:
                        return
                    
                    self.press_to_talk_key_pressed = True
                    self.active_key_down_time = now
                    self.start_recording()
            except Exception as e:
                print(f"⚠️  Error in key press handler: {e}")
                return
        
        def on_key_release(key):
            try:
                if key_matches_target(key, target_key):
                    if not self.press_to_talk_key_pressed:
                        return
                    if not self.is_recording:
                        self.press_to_talk_key_pressed = False
                        return
                    
                    self.press_to_talk_key_pressed = False
                    self.stop_requested = True
                    self.last_toggle_time = time.time()
            except Exception as e:
                print(f"⚠️  Error in key release handler: {e}")
        
        # Start listening for keys
        listener = keyboard.Listener(
            on_press=on_key_press,
            on_release=on_key_release
        )
        listener.start()
        
        # Keep running until exit
        try:
            while not self.should_exit:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n👋 Exiting...")
        finally:
            listener.stop()
            if self.is_recording:
                self.stop_recording()


def main():
    # Check for existing instance
    if not _acquire_lock():
        print("⚠️  Another instance of VoiceType is already running.")
        print(f"   If you're sure no other instance is running, delete: {LOCK_FILE}")
        sys.exit(1)
    
    parser = argparse.ArgumentParser(
        description="VoiceType - Voice-to-Text Input Tool"
    )
    parser.add_argument("--toggle-cooldown", type=float, default=0.3,
        help="Cooldown to ignore rapid key repeats (default: 0.3)")
    parser.add_argument("--min-record-seconds", type=float, default=1.2,
        help="Minimum time to record before a stop is accepted (default: 1.2)")
    parser.add_argument("--post-roll-seconds", type=float, default=0.35,
        help="Extra time to capture after stop to avoid cutting trailing words (default: 0.35)")
    parser.add_argument("--language", type=str, default=None,
        help="Language hint for Whisper (e.g., 'en', 'zh', 'es'). If omitted, Whisper detects automatically.")
    parser.add_argument("--press-to-talk", type=str, required=True,
        help="Enable press-to-talk using this key (hold to record, release to stop). Examples: 'ctrl', 'space', 'q'")
    parser.add_argument("--send-to-active", type=str, choices=["paste", "type"], default="paste",
        help="How to send transcription into the currently focused app: 'paste' (default) or 'type'")
    parser.add_argument("--type-chars-per-sec", type=float, default=30.0,
        help="Typing speed when using --send-to-active type (default: 30 chars/sec)")
    parser.add_argument("--send-delay", type=float, default=0.2,
        help="Delay (seconds) before sending text to allow focus on target field (default: 0.2)")
    parser.add_argument("--model", type=str, default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base)")
    parser.add_argument("--sample-rate", type=int, default=None,
        help="Audio sample rate in Hz (default: auto-detect from device)")
    parser.add_argument("--device", type=int, default=None,
        help="Audio device index (use --list-devices to see available devices)")
    parser.add_argument("--list-devices", action="store_true",
        help="List available audio input devices and exit")
    parser.add_argument("--save-audio-dir", type=str, default=None,
        help="Directory to save audio recordings (optional)")
    parser.add_argument("--save-transcription-dir", type=str, default=None,
        help="Directory to save transcriptions (optional)")
    
    args = parser.parse_args()
    
    if args.list_devices:
        print("Available audio input devices:")
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                default = " (default)" if i == sd.default.device[0] else ""
                print(f"  [{i}] {device['name']}{default}")
        sys.exit(0)
    
    # Create VoiceType instance
    voicetype = VoiceType(
        model_size=args.model,
        sample_rate=args.sample_rate,
        device=args.device,
        save_audio_dir=args.save_audio_dir,
        save_transcription_dir=args.save_transcription_dir
    )
    
    # Configure settings
    voicetype.toggle_cooldown = args.toggle_cooldown
    voicetype.min_record_seconds = args.min_record_seconds
    voicetype.post_roll_seconds = args.post_roll_seconds
    voicetype.language_hint = args.language
    voicetype.send_to_active = args.send_to_active
    voicetype.type_chars_per_sec = args.type_chars_per_sec
    voicetype.send_delay = args.send_delay
    
    # Run press-to-talk
    voicetype.run_press_to_talk(args.press_to_talk)


if __name__ == "__main__":
    main()

