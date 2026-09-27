#!/usr/bin/env bash
# Study a reference launch film in one command.
#   bash skills/launch-review/scripts/study_reference.sh <youtube-or-video-url-or-file> <out-dir> [bpm-guess]
# Produces: ref.mp4 (for study only, never commit it), grids at 2 fps per 16 s, an audio spectrum,
# a whisper transcript with word timings, and the launch-review report (cuts, static runs, loudness,
# onsets, beat offsets, voice pace). Keep the notes and numbers; third-party video stays out of your repo.
# Env: PYTHON (default python3, needs numpy and librosa), WHISPER_MODEL (default <repo>/models/ggml-base.en.bin).
set -euo pipefail
SRC="$1"; OUT="$2"; BPM="${3:-120}"
HERE="$(cd "$(dirname "$0")" && pwd -P)"
SK="$(cd "$HERE/../.." && pwd -P)"
REPO="$(cd "$SK/.." && pwd -P)"
PY="${PYTHON:-python3}"
MODEL="${WHISPER_MODEL:-$REPO/models/ggml-base.en.bin}"
mkdir -p "$OUT"
cd "$OUT"
if [[ -f "$SRC" ]]; then
  cp "$SRC" ref.mp4
else
  # uvx pulls the latest yt-dlp with its EJS solver; node answers the JS challenge.
  uvx --from "yt-dlp[default]" yt-dlp --js-runtimes node -f "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]" \
    --merge-output-format mp4 -o "ref.%(ext)s" "$SRC"
  uvx --from "yt-dlp[default]" yt-dlp --js-runtimes node --print "%(title)s | %(uploader)s | %(duration)s s | %(upload_date)s" "$SRC" > title.txt || true
fi
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 ref.mp4)
for s in $(seq 0 16 "${DUR%.*}"); do
  ffmpeg -v error -y -ss "$s" -t 16 -i ref.mp4 -vf "fps=2,scale=384:-1,tile=8x4" -frames:v 1 "grid-$(printf %03d "$s").jpg"
done
ffmpeg -v error -y -i ref.mp4 -lavfi "showspectrumpic=s=1600x500:legend=0:scale=log:color=intensity" spectrum.png
ffmpeg -v error -y -i ref.mp4 -ac 1 -ar 16000 ref16.wav
whisper-cli -m "$MODEL" -f ref16.wav -nt 2>/dev/null | sed '/^\s*$/d' > transcript.txt || true
"$PY" "$SK/launch-voice/scripts/vo_words.py" ref16.wav words.json --model "$MODEL" || true
"$PY" "$HERE/review.py" ref.mp4 review --bpm "$BPM" --words words.json
rm -f ref16.wav
echo "study ready in $OUT: grids, spectrum.png, transcript.txt, words.json, review/report.md"
