# LowLight Agents

### An agent-based system for enhancing dark and noisy images

Ever taken a photo at night and ended up with something that is **too dark, full of noise, and missing details**?

That is what this project is trying to fix.

Instead of applying the same fixed "brighten + denoise" pipeline to every image, this project uses a small group of agents. Each agent has a specific job: **look at the image, decide what it needs, enhance it, check the result, and try again if necessary.**
Screenshot 2026-09-09 at 18.35.28.png
The main idea is simple:

```text
        ┌──────────────┐
        │  SceneAgent  │
        │ Analyze image│
        └──────┬───────┘
               ↓
        ┌────────────────┐
        │ PlanningAgent  │
        │ Decide what to │
        │ do             │
        └───────┬────────┘
                ↓
        ┌────────────────┐
        │  DenoiseAgent  │
        │ Enhance image  │
        └───────┬────────┘
                ↓
        ┌────────────────┐
        │  ReviewAgent   │
        │ Check result   │
        └───────┬────────┘
                │
          Good enough?
           ↙         ↘
         Yes          No
          ↓            ↓
       Output      Plan again
```

The interesting part is that the system **doesn't assume every image needs the same amount of processing**.

A mildly dark image might only need a small exposure correction, while a very dark and noisy image may need stronger denoising, local contrast enhancement, and another processing attempt.

---

## What does each agent do?

### 1. SceneAgent — "What's wrong with this image?"

The first agent looks at the input image and measures things such as:

* Average brightness
* Contrast
* Estimated noise
* Other basic image statistics

It then turns those measurements into a simple description of the image.

For example:

> "The image is heavily underexposed, has low contrast, and contains noticeable noise."

This gives the next agent something concrete to work with instead of blindly applying filters.

---

### 2. PlanningAgent — "Okay, how should we fix it?"

This agent decides what kind of enhancement the image needs.

Depending on the scene, it can choose things like:

* Gamma correction
* CLAHE / local contrast enhancement
* Denoising method
* Denoising strength
* Sharpening amount

There are two ways the planner can work.

#### LLM mode

If an Anthropic API key is available, the planner can use Claude to reason about the image statistics and decide on an enhancement plan.

The project can also use the notes inside `knowledge/` as additional context for this planning process.

#### Offline mode

No API key? No problem.

The project has a rule-based fallback planner in:

```text
knowledge/heuristics.py
```

This means the project can still run completely without an LLM or internet connection.

---

## 3. DenoiseAgent — "Let's actually fix it."

Once the plan is ready, the DenoiseAgent carries it out using the image-processing tools in `toolbox/`.

The enhancement process can include:

* Gamma correction
* CLAHE
* Noise reduction
* Sharpening

For denoising, the project doesn't depend on just one method.

It tries:

```text
Non-Local Means
       ↓
   if it fails
       ↓
Bilateral Filter
       ↓
   if it fails
       ↓
 Gaussian Blur
```

So if the preferred denoising method doesn't work, the system has a fallback instead of crashing.

---

## 4. ReviewAgent — "Did we actually make it better?"

After enhancement, the image is checked again.

The ReviewAgent looks at things such as:

* Is the brightness in a reasonable range?
* Has the contrast improved?
* Did the noise decrease?
* Was too much detail removed?
* Are highlights getting clipped?

The goal isn't just to make the image brighter.

A brighter image isn't necessarily a **better** image.

For example, aggressive enhancement can make a night photo brighter while also making it noisy, washed out, or full of blown highlights.

The ReviewAgent gives the system feedback about these problems.

---

## The reflection loop

This is where the project becomes more than a simple image-processing pipeline.

If the result isn't good enough, the feedback goes back to the PlanningAgent.

```text
Analyze
   ↓
Plan
   ↓
Enhance
   ↓
Review
   ↓
 ┌───────────────┐
 │ Good enough?  │
 └───────┬───────┘
      Yes│   │No
         ↓   ↓
       Done  Re-plan
              ↓
            Retry
```

The number of retries can be controlled using:

```bash
--max-reflections
```

For example:

```bash
python enhance.py samples/dim_room.jpg --max-reflections 3
```

If the image still doesn't meet the quality requirements after all the attempts, the system falls back to a conservative preset rather than returning an overly aggressive result.

---

# Why low-light images are difficult

Low-light enhancement isn't just about increasing brightness.

When an image is captured in poor lighting, the dark areas can contain a lot of sensor noise. If we simply brighten the image, we also brighten that noise.

For example:

```text
Dark image
    ↓
Increase brightness
    ↓
Dark areas become visible
    ↓
Noise becomes visible too
```

That's why the project considers exposure and denoising together.

A very dark image may need stronger denoising after exposure correction, while a slightly dark image may only need a small adjustment.

---

# Some of the enhancement logic

The project uses simple image statistics to make these decisions.

### Gamma correction

Gamma correction is useful when an image is underexposed.

For moderately dark images, a gamma value around:

```text
0.4 - 0.7
```

can provide a useful brightness lift.

For mildly dark images, a gentler value such as:

```text
0.75 - 0.9
```

is usually enough.

Going too aggressive can make the image look washed out and can also make shadow noise more noticeable.

---

### CLAHE

Gamma correction changes the overall brightness, but it doesn't always recover detail in flat-looking areas.

That's where CLAHE comes in.

CLAHE can improve local contrast and make details easier to see, especially when the image has relatively low contrast.

A reasonable starting point is:

```text
Clip limit: 2.0 - 3.0
Tile grid: 8 × 8
```

The system generally applies gamma correction before CLAHE because lifting the exposure first gives the local contrast enhancement more useful information to work with.

---

### Denoising

The project primarily uses OpenCV's Non-Local Means denoising because it can reduce noise while keeping more image detail than simple blurring.

For moderate noise, a strength around:

```text
8 - 12
```

is a reasonable starting point.

Very strong denoising can remove actual image details, so the ReviewAgent also checks whether the image has been smoothed too aggressively.

---

### Sharpening

Denoising can make an image look slightly soft.

A light sharpening step can bring some of that edge detail back.

The idea is:

```text
Denoise → Light sharpening
```

rather than heavily sharpening the image and bringing all the noise back.

---

# Project structure

```text
lowlight-agents/
│
├── enhance.py
├── config.py
│
├── agents/
│   ├── scene_agent.py
│   ├── planning_agent.py
│   ├── denoise_agent.py
│   ├── review_agent.py
│   └── orchestrator.py
│
├── vision/
│   └── image processing functions
│
├── toolbox/
│   └── image-processing tools
│
├── knowledge/
│   └── heuristics.py
│
├── samples/
│   └── test images
│
├── scripts/
│   └── sample image generation
│
├── tests/
│   └── project tests
│
└── requirements.txt
```

The `knowledge/` Markdown files are only needed if the RAG-based planning path is being used. The core enhancement and denoising system can work without them using the heuristic planner.

---

# Getting started

Install the required packages:

```bash
pip install -r requirements.txt
```

Then run the project on the included sample image:

```bash
python enhance.py samples/dim_room.jpg
```

Or use your own image:

```bash
python enhance.py path/to/your/photo.jpg
```

You can also control the number of reflection attempts:

```bash
python enhance.py path/to/your/photo.jpg \
    --output outputs/fixed.jpg \
    --max-reflections 3
```

The enhanced image and a report describing the processing attempts are saved in the `outputs/` directory.

---

# Using the LLM planner

The LLM-based planner is optional.

If you have an Anthropic API key, you can set it in your terminal:

```bash
export ANTHROPIC_API_KEY="your-api-key"
```

If you don't provide an API key, the project automatically uses the local heuristic planner.

So the project can run in two modes:

```text
             PlanningAgent
                  │
          ┌───────┴───────┐
          ↓               ↓
     Claude + RAG    Heuristic Planner
          │               │
          └───────┬───────┘
                  ↓
            Enhancement
```

This also makes the system usable in environments where internet access or an API key isn't available.

---

# Testing

The project includes synthetic images for testing.

Generate the normal test image:

```bash
python scripts/make_test_image.py
```

Generate a much darker and noisier version:

```bash
python scripts/make_test_image.py --harsh
```

The harsh version is useful for testing whether the reflection loop actually kicks in.

Run the complete test suite with:

```bash
python -m unittest discover -s tests -v
```

---

# What happens when something fails?

The project has multiple fallback layers.

### Planner failure

If the LLM planner isn't available:

```text
LLM Planner
     ↓ fails
Heuristic Planner
```

### Denoiser failure

If Non-Local Means fails:

```text
Non-Local Means
      ↓
Bilateral Filter
      ↓
Gaussian Blur
```

### Enhancement still isn't good enough

If none of the reflection attempts produce a satisfactory result:

```text
Multiple attempts
       ↓
Conservative preset
       ↓
Final output
```

The idea is to make the system **fail gracefully instead of simply crashing**.

---

# Limitations

This project isn't trying to compete with state-of-the-art low-light enhancement models.

The ReviewAgent currently uses explainable image statistics rather than a trained image-quality model.

The noise estimate is also based on **Laplacian variance**, which is only a rough estimate. A highly detailed image can sometimes look "noisy" according to this measurement even when the details are intentional.

The LLM planning mode also requires an API key and network access.

The offline heuristic mode doesn't have those requirements.

---

# Future improvements

There are several directions this project could take.

One obvious improvement would be adding a learned low-light enhancement model to the toolbox.

For example:

```text
                  DenoiseAgent
                       │
        ┌──────────────┼──────────────┐
        ↓              ↓              ↓
   OpenCV NLM      Bilateral      ML Model
```

A Retinex-based or diffusion-based model could be used for images where traditional enhancement methods aren't enough.

Other possible additions include:

* Better no-reference image-quality metrics
* More accurate noise estimation
* GPU acceleration
* Video/night-time enhancement
* Face-aware enhancement
* Automatic parameter learning
* More specialized enhancement tools

Potential applications include **night-time photography, mobile cameras, surveillance footage, and other low-light vision systems**.

---

# The main idea

At its core, this project is about making image enhancement **adaptive instead of fixed**.

Rather than saying:

> "Every dark image gets the same treatment."

the system asks:

> "What is wrong with this particular image, what should I do about it, and did my last attempt actually make it better?"

That's the idea behind the agent-based approach.
