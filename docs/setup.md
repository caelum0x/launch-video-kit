# Setup

Everything runs locally. The free path (your brand, a type-only hook, a scratch voice, a scratch music bed, the synthesised sound palette) needs no account. Paid generation runs on your own Higgsfield account.

## What you need

| Tool | Why | Required |
|---|---|---|
| Node.js 20 or later, npm | the brand extractor and HyperFrames (the renderer) | yes |
| ffmpeg | every audio and video step | yes |
| Python 3.10 or later and [uv](https://docs.astral.sh/uv/) | the audio pipeline (voice prep, sound, mix, review) | yes |
| whisper.cpp (`whisper-cli`) and a model | checking and timing the spoken words | yes for real voice takes |
| torch and torchaudio | forced alignment, the precise word timing | recommended, pulled on demand by `uv` |
| Higgsfield CLI and account | narrator voice, music, sound kits, generated footage | optional |
| Blender 5.x | 3D glass objects | optional |
| ACE-Step 1.5 | free local music takes | optional |
| Dragonfly Plate Reverb (VST3) | the shared reverb for sound effects; a built-in reverb is used without it | optional |

## macOS

```bash
brew install node ffmpeg uv whisper-cpp
npm install                                   # installs the brand extractor's headless browser
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt
mkdir -p models
curl -L -o models/ggml-base.en.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
curl -L -o models/ggml-small.en.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin   # better on product names
```

The scratch voice uses macOS `say`, which is already installed. HyperFrames downloads its own headless Chrome on the first render (`npx -y hyperframes@0.8.77 ...`).

## Linux

```bash
sudo apt install ffmpeg espeak-ng build-essential cmake    # espeak-ng is the scratch voice
curl -LsSf https://astral.sh/uv/install.sh | sh
# Node 20+: from nodesource or nvm
git clone https://github.com/ggml-org/whisper.cpp ~/whisper.cpp
cmake -S ~/whisper.cpp -B ~/whisper.cpp/build && cmake --build ~/whisper.cpp/build -j
export PATH="$HOME/whisper.cpp/build/bin:$PATH"            # provides whisper-cli
```

Then the same `npm install`, venv and model steps as on macOS. Headless Chrome needs the usual system libraries (`libnss3`, `libatk-bridge2.0-0`, `libgbm1`, `libasound2` and friends); if a render fails to launch the browser, install those.

## Environment variables

| Variable | Default | Used by |
|---|---|---|
| `WHISPER_MODEL` | `models/ggml-base.en.bin` in the repo | voice scripts, reference study |
| `REVERB_VST3` | `~/Library/Audio/Plug-Ins/VST3/DragonflyPlateReverb.vst3` | `sfx_forge.py` |
| `ACE_STEP_ROOT` | `~/ACE-Step-1.5` | `ace_score.py` |
| `BLENDER_GPU` | `METAL` (`CUDA`, `OPTIX` or `NONE` elsewhere) | `blender_glass_object.py` |
| `PYTHON` | `python3` | `study_reference.sh` |

## Optional tools

- **Forced alignment:** nothing to install by hand. `uv run -q --with torch --with torchaudio --with soundfile python skills/launch-voice/scripts/force_align.py LINE.wav "the words"` pulls torch on first use and caches the aligner model (about 1.2 GB) in `~/.cache/torch`.
- **Higgsfield:** `npm install -g @higgsfield/cli`, then `higgsfield auth login` with your own account. Check your balance with `higgsfield account status`. For deeper Higgsfield know-how, add their skills: `npx skills add higgsfield-ai/skills`.
- **HyperFrames skills:** `npx skills add heygen-com/hyperframes` gives your agent the full composition contract, motion catalog and CLI docs.
- **Blender:** install 5.x from blender.org (macOS: `brew install --cask blender`).
- **ACE-Step 1.5:** follow its README to install it into its own folder with its own venv, then set `ACE_STEP_ROOT`. Models download on first run (several GB).
- **Dragonfly Reverb:** free and open source (GPL); install the VST3 plug-in from its website. Without it the sound palette uses pedalboard's built-in reverb.
- **Local voice clone:** `skills/launch-voice/scripts/clone_local.py` pulls Chatterbox through `uv` on first run (a few GB).

## Check the install

```bash
node -v && ffmpeg -version | head -1 && whisper-cli --help | head -1
source .venv/bin/activate && python3 -c "import numpy, scipy, soundfile, pedalboard, pyloudnorm, librosa; print('audio ok')"
python3 skills/launch-sound/scripts/sfx_forge.py palette /tmp/palette --key A    # 13 sounds, free
```
