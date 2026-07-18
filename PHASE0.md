# Phase 0 — first working video

Goal: one playable mp4. 15s, English, 3 scenes, 9:16, Wan 1.3B, on RunPod.

## What "success" means here

**Judge this on sync, not beauty.**

- ✅ Audio, subtitles and video stay locked together
- ✅ QC gates pass
- ✅ Every stage produced a real file
- ❌ NOT "does it look cinematic" — Wan 1.3B does not make cinematic video and
  is not being asked to. Beauty is Phase 6 (14B), and that is a cost decision
  made later with real data.

Concluding "the project failed" from a rough-looking Phase 0 clip would be the
wrong read. What is being proven is that the pipeline is honest: when it says
completed, a file exists, and its parts line up.

> ⚠️ **This code has never been executed.** It was written on a machine with no
> Python and no Docker, so it is not even syntax-checked. Expect real bugs on
> first run. Step 1 below exists to catch them cheaply, before any GPU spend.

---

## Step 1 — run the tests first (no GPU, ~2 min)

Do this anywhere, including your laptop. It needs no models and no GPU.

```bash
cd backend
pip install pytest pytest-asyncio structlog pydantic pydantic-settings httpx
pytest tests/ -v
```

These cover the logic that silently breaks videos: timing reconciliation,
language routing, subtitle placement, license gating. If something here fails,
fix it before renting a GPU — a bug found in 2 minutes on a laptop is a bug not
found in 20 minutes at $0.40/hr.

## Step 2 — a RunPod box

- **GPU:** RTX 4090 or A10G (24GB). Wan 1.3B needs ~8.2GB; FLUX and Stable Audio
  share the card.
- **Template:** a PyTorch 2.4 + CUDA 12.1 image
- **Disk:** 60GB+ (weights are large)
- **Cost:** roughly $0.30–0.50/hr — verify current pricing, it moves

## Step 3 — set up

```bash
apt-get update && apt-get install -y ffmpeg      # the compositor needs this
git clone <your-repo> && cd dev-video.zapkitt.com/backend
pip install -r requirements.txt

cp ../.env.example ../.env
# Set LLM_API_KEY — free key from https://console.groq.com
```

First run downloads Wan 1.3B (~6GB), Stable Audio (~5GB) and Whisper base
(~150MB) — roughly 11GB. (FLUX is NOT downloaded: Phase 0 uses Wan text-to-video
directly. FLUX enters at the image-to-video/consistency phase.) Budget ~10
minutes for the download, once per box. Phase 4 bakes these into an AMI so
scale-up isn't paying this every time.

## Step 4 — generate

```bash
python run_phase0.py "A farmer in rural India discovers online coding classes and changes his life"
```

Output lands in `/tmp/render/phase0/`:

```
final.mp4            ← the deliverable
subtitles.srt
bgm.wav
scene_1_voice.wav    scene_1_clip.mp4
scene_2_...          scene_3_...
```

Every intermediate is kept deliberately. When something looks wrong, you need to
know *which stage* did it — that is what the admin dashboard formalises later
(ARCHITECTURE.md §9).

## Step 5 — read the output

```
✓ /tmp/render/phase0/final.mp4
  Duration: 16.4s  (planned 15.0s, drift +1.4s)
  QC:       QC passed (6 checks)

  Stage timings:
    script             3.2s
    voice_reconcile   11.8s
    align              6.1s
    video            420.3s      ← dominates, as expected
    music             38.7s
    compose            9.4s
```

**Drift of +1.4s is normal and correct.** The script agent's pacing is a guess;
reconcile measured the real speech and re-timed the video to match. That is the
system working. A drift of 0.0s every run would be suspicious.

---

## Expected failures, and what they mean

| Symptom | Cause | Fix |
|---|---|---|
| `UnsupportedCapability: No TTS provider supports 'te'` | Asked for Telugu | Working as designed. Telugu is Phase 2 (IndicF5). Kokoro has no Telugu. |
| `ffmpeg not found on PATH` | Step 3 skipped | `apt-get install -y ffmpeg` |
| `CUDA out of memory` | Wan + Stable Audio on one card | Both are small (~8GB + ~8GB); a 24GB card fits them. If it persists on a smaller card, drop `--scenes` to 2. |
| `QC FAILED: black_frames` | Video model failed a scene | Inspect `scene_N_clip.mp4`. A 1.3B failure mode. |
| `QC FAILED: silence` | TTS produced empty audio | Check `scene_N_voice.wav`. Usually a bad script line. |
| `LLM returned invalid JSON` | Groq drifted from format | Re-run. Persistent → tighten `script_stage.py` SYSTEM. |
| `subtitle_drift` fails | Something re-timed cues after alignment | A real bug — that gate should be ~0 by construction. |

Use `--no-strict-qc` to force the file out for inspection when a gate fails.

---

## When Phase 0 is green

1. Watch it. Are voice, subtitles and visuals locked? That is the only question.
2. If yes → **Phase 1**: 60s, act-based music with crossfades, per-scene retry.
3. File the **AWS G-instance quota request now** if you haven't. It takes days
   and blocks Phase 4. Costs nothing to ask early.
4. Start thinking about **voice talent** (ARCHITECTURE.md §12 decision 3) — it
   is Phase 3's long pole and needs recorded consent, not just a decision.

## What Phase 0 deliberately does NOT do

Not scope cuts — sequencing. Each needs Phase 0 to be green first.

- **Telugu / Hindi** — Phase 2. Needs IndicF5 + reference voices + consent.
- **Character consistency** — Phase 3. `character_packs/` has 0 reference images
  for 15 described characters; there is nothing to be consistent about yet.
- **Lip sync** — Phase 3.
- **Multiple aspect ratios** — Phase 5. Ratio is a generation input, not a crop.
- **AWS** — Phase 4. RunPod is cheaper for iteration and needs no quota.
