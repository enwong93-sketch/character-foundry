# Character Foundry

Build T-pose 3D characters with a coding agent.

1. Generate a standardized Master and three reference images with structured Image Gen prompts.
2. Generate and inspect each mesh in Tripo Studio using Smart Mesh P2.0.
3. Verify local downloads and review each imported part in Blender.
4. Repair confirmed defects, including automatic correction of reversed faces on unrigged GLBs.
5. Manually place the parts in Blender, inspect the joins through 360°, and match skin tone where needed.

Clone this repository into a skill folder named `tripo-to-blender-workflow`, or point your agent at [SKILL.md](SKILL.md). Keep the `references/` and `scripts/` directories alongside it. You need an image generation tool, access to Tripo Studio, Blender, and Python 3.10 or later.

The deliverables are reviewed source parts, an assembled Blender file with separate parts, and verification records. Steps 1–4 also work on their own when only the parts are needed. The workflow ends with a static assembly review before rigging.

[MIT License](LICENSE)
