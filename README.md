# VoiceType

**Voice-to-Text Input Tool** - Press-to-talk voice transcription that types directly into your active application.

## Features

- 🎙️ **Press-to-Talk**: Hold a key to record, release to transcribe
- 🧠 **Whisper AI**: Powered by OpenAI's Whisper for accurate transcription
- ⌨️ **Direct Input**: Automatically types or pastes transcription into the active app
- 🌐 **Multi-Language**: Supports multiple languages (auto-detected or specified)
- 💾 **Optional Recording**: Save audio and transcriptions for later review

## Requirements

- Python >=3.10, <3.15

## Quick Start

### Installation

1. Create a virtual environment (recommended):
```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Running the Menu Bar App (Recommended)

The easiest way to use VoiceType is through the macOS menu bar app:

**Option 1: Using the bash script (easiest):**
```bash
./run.sh
```

**Option 2: Direct Python command:**
```bash
python run_app.py
```

This will:
- Show a 🎤 icon in your menu bar
- Auto-start VoiceType on launch
- Provide a menu with Start/Stop, Settings, and Quit options
- Allow you to customize the press-to-talk key through Settings

### Running the Command Line Version

For command-line usage:

```bash
python voicetype.py --press-to-talk ctrl --send-to-active paste
```

### Basic Usage

**Press-to-talk with paste (recommended):**
```bash
python voicetype.py --press-to-talk ctrl --send-to-active paste --send-delay 0.2
```

**Press-to-talk with typing:**
```bash
python voicetype.py --press-to-talk space --send-to-active type --type-chars-per-sec 30
```

**With language hint:**
```bash
python voicetype.py --press-to-talk ctrl --language en --send-to-active paste
```

## Command Line Options

### Required
- `--press-to-talk KEY`: Key to hold for recording (e.g., `ctrl`, `space`, `q`)

### Optional
- `--send-to-active {paste,type}`: How to send text (default: `paste`)
- `--send-delay SECONDS`: Delay before sending text (default: `0.2`)
- `--type-chars-per-sec RATE`: Typing speed when using `type` mode (default: `30`)
- `--language LANG`: Language hint (e.g., `en`, `zh`, `es`) - auto-detected if omitted
- `--model {tiny,base,small,medium,large}`: Whisper model size (default: `base`)
- `--min-record-seconds SECONDS`: Minimum recording duration (default: `1.2`)
- `--post-roll-seconds SECONDS`: Extra time after stop to capture trailing words (default: `0.35`)
- `--toggle-cooldown SECONDS`: Cooldown to prevent rapid toggles (default: `0.3`)
- `--save-audio-dir DIR`: Directory to save audio recordings
- `--save-transcription-dir DIR`: Directory to save transcriptions
- `--list-devices`: List available audio input devices
- `--device INDEX`: Audio device index (use `--list-devices` to find)
- `--sample-rate HZ`: Audio sample rate (auto-detected if omitted)

## Examples

### Example 1: Basic Dictation
```bash
# Hold Ctrl to record, release to transcribe and paste
python voicetype.py --press-to-talk ctrl
```

### Example 2: Fast Typing
```bash
# Use spacebar, type at 50 chars/sec
python voicetype.py --press-to-talk space --send-to-active type --type-chars-per-sec 50
```

### Example 3: Save Everything
```bash
# Save all recordings and transcriptions
python voicetype.py --press-to-talk ctrl \
  --save-audio-dir ./recordings \
  --save-transcription-dir ./transcriptions
```

### Example 4: High Accuracy
```bash
# Use larger model for better accuracy (slower)
python voicetype.py --press-to-talk ctrl --model small --language en
```

## How It Works

1. **Press and Hold**: Hold your configured key (e.g., Ctrl) to start recording
2. **Speak**: Speak naturally while holding the key
3. **Release**: Release the key to stop recording
4. **Transcribe**: Whisper transcribes your speech
5. **Input**: The transcription is automatically pasted or typed into the active application

## macOS Permissions

VoiceType requires the following macOS permissions:

1. **Microphone**: For audio recording
   - System Settings > Privacy & Security > Microphone

2. **Accessibility**: For typing/pasting into apps
   - System Settings > Privacy & Security > Accessibility

3. **Input Monitoring**: For keyboard input detection
   - System Settings > Privacy & Security > Input Monitoring

## Tips

- **Paste mode** (default) is faster and more reliable than typing mode
- Use `--send-delay 0.3` if text fields need time to focus
- For better accuracy, use `--model small` or `--model medium` (slower but more accurate)
- Add `--language en` if you primarily speak English for faster transcription
- Use `--post-roll-seconds 0.5` if trailing words are being cut off

## Troubleshooting

**No audio detected:**
- Check microphone permissions
- Use `--list-devices` to see available devices
- Try specifying `--device INDEX` explicitly

**Text not appearing in app:**
- Check Accessibility permissions
- Increase `--send-delay` to allow time for focus
- Try `--send-to-active type` instead of `paste`

**Transcription accuracy low:**
- Use a larger model: `--model small` or `--model medium`
- Add language hint: `--language en`
- Increase `--post-roll-seconds` to capture trailing words

## License

This project is provided as-is for personal use.

