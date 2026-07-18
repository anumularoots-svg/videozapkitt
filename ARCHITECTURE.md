# AI Video Compiler — Architecture

Target: idea or script → finished video (visuals + character + voice + lip-sync + BGM + subtitles),
multi-language (English / Hindi / Telugu first), multi-aspect-ratio, three authoring modes.

This document is the build plan. It replaces the aspirational claims in `README.md`, which
describes a system that does not exist yet (see "Current State" below).

---

## 0. Current State — what actually exists

Measured by reading the code, not the README:

| Component | Claimed | Actual |
|---|---|---|
| Script generation | ✅ | ✅ Real LLM HTTP call (`agents/llm_client.py`) |
| Subtitle SRT | ✅ | ⚠️ Real SRT writer, but timings are guessed, not aligned to audio |
| FFmpeg render | ✅ | ⚠️ Real code, **never called by anything** |
| Voice generation | ✅ | ❌ Builds a dict describing a task. No TTS call. |
| Music generation | ✅ | ❌ Builds a prompt string. No audio model call. |
| Scene video | ✅ | ❌ Comment block, returns `{"status": "completed"}` |
| Character packs (15) | ✅ | ❌ 1 metadata file, 0 reference images |
| Translation (NLLB) | ✅ | ❌ Model name in config, zero code |
| Lip sync | — | ❌ Not present |
| Terraform | ✅ | ❌ Placeholder AMI, no ECS/IAM/SG/ALB. Will not apply. |

**Nothing generates media.** The DAG marks video/render/export tasks successful without doing
work (`orchestrator/dag_orchestrator.py`), which is why the pipeline "passes" while producing
no file. Treat the current repo as a naming convention and a directory layout — roughly 5% of
the target system, and the 5% that was easiest.

---

## 1. The three constraints that shape every decision

Everything below follows from these. They are not negotiable by wishing.

### 1.1 "Free + 100% accurate + all languages" is not a reachable point

No TTS or video model — free or paid — is 100% accurate. The honest, *measurable* target is:

- **Voice**: native speaker rates it natural; pronunciation error rate below a set threshold
- **Lip sync**: sync offset within ~80ms
- **Subtitles**: word timings within ~120ms of audio (achievable — forced alignment is exact enough)
- **Character consistency**: face embedding similarity above a threshold across scenes
- **Visual**: no automated metric is trustworthy; needs human spot-check

Design principle: **every stage emits a numeric quality score, and the pipeline fails loudly
below threshold rather than shipping a bad video.** "100% accuracy" becomes "0% silent failures"
— that IS achievable, and it is what actually protects the product.

### 1.2 GPU is the cost center, and the model tier decides the bill

Verified numbers:

| Model | VRAM | AWS instance | Reality |
|---|---|---|---|
| Wan 2.1 **T2V-1.3B** | ~8.2 GB | g5.xlarge (A10G 24GB) | Runs comfortably. Quality: decent, not cinematic. |
| Wan 2.1 **I2V-14B** @480p FP8 | **40–48 GB** | g5.12xlarge / A100 | 5–10× the cost. Broadcast quality. |
| Wan 2.1 **14B** @720p | 65–80 GB | A100 80GB | Not a dev-budget option. |

Your `.env.example` currently specifies `Wan2.1-T2V-14B`. That choice alone is the difference
between a ~$0.30/hr dev box and a ~$5/hr one. **This is decision #1 and it is yours to make.**

> Practical blocker: new AWS accounts often have a **G/VM instance quota of 0**. Requesting an
> increase takes days. File this request *now*, before any code is ready — it is the longest
> lead-time item in the whole project.

### 1.3 Video models generate ~5-second clips

A 60s video = 12+ independently generated clips that must hold the same character, lighting,
and wardrobe. **This is the hardest unsolved part of the project**, not the AWS deployment.
Character drift across clips is the single most likely reason the output won't feel "like a movie."

Mitigation stack (in order of leverage): keyframe-first generation → IP-Adapter/InstantID
identity conditioning → last-frame-of-clip-N as first-frame-of-clip-N+1 → per-scene face
similarity gate with auto-retry.

---

## 2. Model stack (license-verified)

License matters because you plan a subscription product. Non-commercial weights are a lawsuit,
not a shortcut.

| Capability | Model | License | Commercial? |
|---|---|---|---|
| Script LLM | Llama 3.3 70B via Groq free tier | Llama license | ✅ (under 700M MAU) |
| Keyframe image | **FLUX.1-schnell** | Apache 2.0 | ✅ |
| ~~Keyframe~~ | ~~FLUX.1-dev~~ | Non-commercial | ❌ **avoid** |
| Video | **Wan 2.1** (1.3B or 14B) | Apache 2.0 | ✅ |
| TTS English | **Kokoro-82M** | Apache 2.0 | ✅ |
| TTS Telugu/Hindi | **IndicF5** (AI4Bharat) | MIT | ✅ ⚠️ see note |
| Alignment/subtitles | **Whisper** | MIT | ✅ |
| Music | **Stable Audio Open** | Stability Community | ✅ under $1M revenue |
| ~~Music~~ | ~~MusicGen~~ | CC-BY-NC | ❌ **avoid** |
| Lip sync | LatentSync / SadTalker | verify per-repo | ⚠️ verify before committing |
| Upscale | Real-ESRGAN | BSD-3 | ✅ |

**Telugu is solved — but not by Kokoro.** Kokoro officially covers 8 languages; Telugu is not
among them, and its Hindi is trained on single-digit hours (quality ~B-). **IndicF5** is trained
on 1417 hours across 11 Indian languages including Telugu, and is MIT licensed.

> ⚠️ IndicF5 is a *reference-voice* (few-shot cloning) model. You must have explicit permission
> for any voice you use as a reference. For a commercial product this means **recording your own
> voice talent** for the 15 characters and holding signed releases. Budget for this — it is a
> real dependency, not a technical detail.

**Licensing rule for the repo:** every provider class declares its license in code, and CI fails
if a non-commercial model is wired into a commercial code path.

---

## 3. Core abstraction: capability providers

The single most important design decision. You *will* swap Kokoro→IndicF5, 1.3B→14B,
Stable Audio→something else. Hardcoding model calls into agents (as the current code hints at)
makes every swap a rewrite.

```python
class TTSProvider(Protocol):
    def capabilities(self) -> Capabilities: ...   # languages, sample rate, cloning support
    async def synthesize(self, req: TTSRequest) -> AudioAsset: ...

@dataclass(frozen=True)
class Capabilities:
    languages: frozenset[str]
    license: License          # commercial-safe or not
    max_duration_s: float | None
    aspect_ratios: frozenset[str] | None
```

A **router** picks the provider by requested capability:

```python
def route_tts(language: str) -> TTSProvider:
    for p in TTS_PROVIDERS:
        if language in p.capabilities().languages:
            return p
    raise UnsupportedCapability(f"No TTS provider supports {language!r}")
```

**This directly fixes a live bug.** Today `agents/voice/agent.py` accepts a `language` field and
then ignores it — all 15 voice presets are English (`am_adam`, `af_sarah`, …). Ask it for Telugu
and it silently narrates in English. Under the router, that raises instead. **Fail loud, never
silently wrong** — this is the rule that makes "100% accuracy" mean something.

Providers needed: `LLMProvider`, `TTSProvider`, `ImageProvider`, `VideoProvider`,
`MusicProvider`, `LipSyncProvider`, `AlignmentProvider`, `UpscaleProvider`.

---

## 4. Pipeline

```
intake → script → scene plan → character resolve → keyframes
   → voice → ⟨TIMING RECONCILE⟩ → alignment → video → lip-sync
   → music → composite → QC gate → export×N ratios
```

### 4.1 Intake
`{ mode, idea | script, duration, language, aspect_ratios[], style }`

### 4.2 Script → scene plan
LLM emits scenes with: dialogue, visual prompt, character id, emotion, camera, environment,
music mood, planned duration.

### 4.3 Timing reconciliation ← *the stage the current design is missing*

The planner assigns a scene 5.0s. The TTS then produces 6.3s of speech. Current code never
compares them — so audio, subtitles, and video drift apart, and the drift **accumulates**
across scenes. By scene 10 the video is visibly broken.

**Voice is the clock.** Generate voice first, measure real duration, then re-time scenes to it:

```python
for scene in scenes:
    audio = await tts.synthesize(scene.dialogue, lang)
    scene.actual_duration = audio.duration      # truth
    if scene.actual_duration > scene.planned * 1.25:
        scene.dialogue = await llm.shorten(scene.dialogue, target=scene.planned)
        audio = await tts.synthesize(scene.dialogue, lang)   # regenerate
        scene.actual_duration = audio.duration
    scene.video_duration = scene.actual_duration + PAD_S
```

Then generate video to `actual_duration`. Never the reverse.

> Language note: the same sentence in Telugu vs English differs in spoken length by a wide
> margin. A fixed words-per-second constant (the current code uses 2.5) cannot hold across
> languages. Measure; don't estimate.

### 4.4 Alignment (subtitles)
Whisper forced-alignment on the *generated* audio → word-level timings. Exact by construction.
Current code divides scene time evenly across chunks — guaranteed drift. Delete that approach.

### 4.5 Video
Keyframe (FLUX.1-schnell + IP-Adapter for identity) → Wan 2.1 I2V → clip. Chain last frame →
next first frame for continuity. Face-similarity gate; retry on drift.

### 4.6 Music
Stable Audio Open caps around ~47s, so a 60s video needs stitching. Generate **per act** (2–3
segments, not per scene — per-scene music is jarring), crossfade at act boundaries.

### 4.7 Composite (FFmpeg)
Fix in flight: the current pipeline uses static `volume=0.3` for music. Use **sidechain ducking**
so music dips under speech dynamically — a large, cheap perceived-quality win:

```
[music][voice]sidechaincompress=threshold=0.03:ratio=8:attack=5:release=250[ducked];
[voice][ducked]amix=inputs=2:duration=first
```

### 4.8 QC gate
Automated, blocking: audio/video duration match · lip-sync offset · face similarity per scene ·
subtitle-vs-audio alignment · loudness (**-14 LUFS** for social) · black-frame / silence detection.
Below threshold → retry that scene, not the whole video.

---

## 5. Aspect ratios

Cropping 9:16 → 16:9 destroys the composition (you keep a thin horizontal band). Cropping
16:9 → 9:16 keeps the subject and works.

**Rule:** aspect ratio is a *generation input*, not a post-process.

- Single-ratio delivery → generate natively at that ratio.
- Multi-ratio delivery → generate a **16:9 master**, then reframe to 9:16 / 1:1 / 4:5 using
  subject-tracked crop (face detection drives the crop center).

| Target | Ratio | Resolution |
|---|---|---|
| YouTube Shorts / IG Reel / TikTok | 9:16 | 1080×1920 |
| YouTube long | 16:9 | 1920×1080 |
| IG feed | 4:5 | 1080×1350 |
| Square | 1:1 | 1080×1080 |

---

## 6. Modes

| Mode | User provides | System does |
|---|---|---|
| **auto** | idea line | everything: script, scenes, characters, visuals, voice, BGM |
| **hybrid** | idea + style | style selects checkpoint/LoRA + prompt template: realistic, 2D, 3D, anime, comic |
| **manual** | own character images, per-scene overrides | uses uploads as IP-Adapter identity reference |

Style is a **registry entry**, not an if-branch: `{checkpoint, lora, prompt_prefix, negative_prompt, sampler}`.
Adding "comic" must be a config row, never a code change.

Manual mode needs an upload path with **consent tracking** — the same constraint as voice cloning.

---

## 7. AWS design

```
Route53 → CloudFront → S3 (Next.js static)
                    └→ ALB → ECS Fargate (FastAPI)  → RDS Postgres (t4g.micro dev)
                                                     → ElastiCache Redis (t4g.micro)
                                                     → S3 (assets)
                                                     → SQS ──┐
                                                             ↓
                                   ASG (min=0) → EC2 GPU spot → Celery worker
                                                             ↑ scale on queue depth
```

**Non-negotiable: GPU ASG scales to zero.** An idle GPU box is the fastest way to burn the
budget. `min_size = 0`, scale on SQS `ApproximateNumberOfMessagesVisible`.
The current Terraform sets `desired_capacity = 0` with **no scaling trigger wired** — workers
would never start at all.

**Model weights:** Wan 2.1 14B is ~28GB+. Downloading at boot adds minutes to every scale-up.
Bake weights into a **custom AMI** (or EBS snapshot). Build it in CI with Packer.

**Dev environment specifically:**
- Everything except GPU on free-tier / smallest instances
- GPU worker on **spot**, scale-to-zero
- `environment = "dev"` (current Terraform defaults to `"production"`)
- Rough cost: ~$30–50/mo idle + GPU burn per video

> **Cost-honest recommendation:** for the *build and test* phase, AWS GPU is the expensive way
> to iterate. **RunPod / Vast.ai** cost a fraction and need no quota request. Build the pipeline
> there, move to AWS once it produces good video. The provider abstraction (§3) makes the worker
> host irrelevant — that is a large part of why it exists.

### Terraform gaps to close
Real AMI id · ECS task definitions + IAM task roles · security groups (RDS must **not** be
public) · ALB + target groups · RDS subnet group + Secrets Manager for the password ·
SQS→ASG scaling policy · CloudWatch alarms · S3 lifecycle (expire scratch renders) ·
remote state (S3 + DynamoDB lock).

---

## 8. Repo layout

```
backend/
  providers/           # ← the swap layer
    llm/  tts/  image/  video/  music/  lipsync/  align/  upscale/
    base.py            # Protocols + Capabilities + License
    registry.py        # capability-based routing
  pipeline/
    stages/            # one file per stage; each is pure + independently testable
    graph.py           # DAG definition
    reconcile.py       # §4.3 — voice-is-the-clock
  qc/                  # §4.8 gates + thresholds
  compose/             # FFmpeg graph builders
  api/  models/  workers/  storage/
frontend/              # Next.js — creator UI
admin/                 # Next.js — ops dashboard
infrastructure/
  terraform/{modules,envs/{dev,prod}}
  packer/              # GPU AMI with baked weights
  docker/
character_packs/       # 15 chars × {reference images, voice samples, consent record}
```

## 9. Admin dashboard

Not optional — without it you cannot answer "why is this video bad?"

Per job: stage timings · GPU seconds · **cost** · QC scores per scene · model+version per stage ·
seed · retry count · asset browser (every intermediate: keyframe, clip, voice wav, bgm) ·
one-click scene re-generate.

Fleet: queue depth · spot interruptions · cost/day · QC pass rate trend · failure taxonomy.

**Every asset records the model, version, and seed that produced it.** Without this, quality
regressions are unfixable.

## 10. CI/CD (GitHub Actions)

`lint → unit → license-check → build+push ECR → terraform plan (PR comment) → apply on merge → smoke`

Plus a **nightly golden-set run**: generate the same 5 fixed prompts, assert QC scores don't
regress, post the videos as artifacts. This is how you catch "video got worse" — which normal
tests never catch.

`license-check` fails the build if a non-commercial model reaches a commercial path.

---

## 11. Roadmap — strictly ordered

Each phase produces something watchable. Do not start a phase before the previous one is green.

- **Phase 0 — Vertical slice.** 15s, English, 1 character, 3 scenes, 9:16, local/RunPod GPU,
  Wan 1.3B. **Exit: a playable mp4 with visuals + voice + BGM + subtitles.** Nothing else
  matters until this exists. This is where the current repo should have started.
- **Phase 1 — Correctness.** Timing reconciliation, Whisper alignment, QC gate, ducking.
  Exit: audio/subs/video stay locked across 60s.
- **Phase 2 — Languages.** IndicF5 for Telugu + Hindi. Native-speaker review.
  Exit: Telugu video a native speaker calls natural.
- **Phase 3 — Character + lip sync.** 15 packs w/ reference images + recorded voice + consent.
  IP-Adapter identity chain, face-similarity gate, LatentSync. Exit: same face across 12 clips.
- **Phase 4 — AWS dev.** Terraform gaps closed, GPU AMI, scale-to-zero, CI/CD, admin dashboard.
- **Phase 5 — Modes & ratios.** Hybrid styles, manual upload, multi-ratio reframe.
- **Phase 6 — Quality tier & subscription.** Evaluate 14B vs 1.3B on cost/quality. Billing, quotas.

**Phase 0 is the whole risk.** If Wan 1.3B output isn't good enough at 15s, no amount of AWS,
dashboards, or Terraform fixes that — and you'll know in days instead of months.

---

## 12. Decisions

### Settled

| # | Decision | Choice | Consequence |
|---|---|---|---|
| 1 | Dev GPU host | **RunPod / Vast.ai** for Phase 0–3 | Start immediately, no quota wait. AWS quota request filed in parallel so Phase 4 isn't blocked. §3 provider abstraction keeps the host swappable. |
| 2 | Model tier | **Wan 2.1 1.3B** for Phase 0 | ~8GB VRAM, cheap+fast iteration. Goal is pipeline *correctness*, not beauty. Re-evaluate 14B at Phase 6 with real cost/quality data. |
| 3 | Voice talent | **Deferred** | Phase 0–1 run English-only on Kokoro (Apache 2.0, no reference voice needed). Must be settled before Phase 3 — it is that phase's long pole. |

> Decision 2 implies **Phase 0 output will not look cinematic, and that is expected.** Judge
> Phase 0 on "do audio, subtitles, video, and music stay locked together?" — not on beauty.
> Judging 1.3B output on beauty and concluding the project failed would be the wrong read.

> Decision 3 implies Phase 0–1 have **no Telugu**. That is deliberate sequencing, not a
> descope: IndicF5 needs reference voices, and reference voices need consent. English proves
> the pipeline; Telugu proves the language layer. Don't fight both at once.

### Still open (not yet blocking)

4. **"Free" boundary** — Groq free tier has rate limits; at scale you self-host or pay. Where's the line?
5. **Music licensing** — Stable Audio Open is free under $1M revenue. Above it, renegotiate. OK?
6. **AWS quota request** — file the G-instance increase now (§1.2). Longest lead-time item; costs nothing to request early.

---

## 13. Sources

- [Kokoro-82M VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md) — language coverage
- [Kokoro Hindi quality discussion](https://huggingface.co/hexgrad/Kokoro-82M/discussions/88)
- [ai4bharat/IndicF5](https://huggingface.co/ai4bharat/IndicF5) — MIT, 11 Indian languages, 1417h
- [Wan-AI/Wan2.1-I2V-14B-480P](https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P) — Apache 2.0
- [Wan 2.1/2.2 VRAM requirements](https://willitrunai.com/blog/wan-2-2-vram-requirements)
