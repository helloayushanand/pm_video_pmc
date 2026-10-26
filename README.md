# Model configuration

Visual component repair uses a separate model from component generation and
visual QA. By default, repair uses `gpt-5`; the pipeline runner routes this
setting directly to repair instead of overriding it with the general model.
Set `OPENAI_VISUAL_REPAIR_MODEL` in `.env` to another model available to your
API account if needed. `OPENAI_MODEL` continues to control generation and QA.
The full pipeline makes one visual-repair attempt per scene. After repair, it
re-reviews and recompiles changed components, then renders and assesses
previews again. Repair guidance includes defect-specific actions, such as
removing opacity fades from text when low contrast is detected during a reveal.
The pipeline stops with the unapproved scene IDs if visual QA still fails or
no valid repair can be produced.

```dotenv
OPENAI_MODEL=gpt-5-mini-2025-08-07
OPENAI_VISUAL_REPAIR_MODEL=gpt-5
```

Planned decorative images are generated automatically during a new run. Use
`--skip-image-generation` to avoid that image-generation step. Extracted dossier
images are visually checked with `OPENAI_MODEL`; a verified candidate headshot
is automatically selected for the intro, while unrelated images are not
treated as portraits or generic brand assets. If no headshot is verified, the
planned portrait treatment remains the fallback. Generated components are
automatically approved for compilation only after deterministic source
validation passes; preview and final-video visual QA remain publication gates.
Automatic image generation and visual headshot selection use the configured
OpenAI models and incur their normal API costs.

The standard pipeline selects up to five Creative Director-approved scenes
for generated components (rather than the previous two-scene cap). Generated
and library scenes share the same background treatment, brand chrome,
typography, and theme colors; QA rejects clear design-system breaks. Scenes
that fail review or rendering still use their safe library fallback.

Visual QA only blocks publication for concrete blocking defects or scores
below its defined thresholds. Non-blocking warnings are retained in the QA
report and do not by themselves reject an otherwise usable scene.