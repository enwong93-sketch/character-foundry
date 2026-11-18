# Tripo to Blender Workflow

An MIT-licensed Agent Skill for coding agents preparing independent Hair, Head, and Body meshes for Blender.

1. Generate a standardized Master and three reference images with structured Image Gen prompts.
2. Generate and inspect each mesh in Tripo Studio using Smart Mesh P2.0.
3. Verify local downloads and review each imported part in Blender.
4. Repair confirmed defects, including automatic correction of reversed faces on unrigged GLBs.

Clone this repository as a skill folder for your agent, or point your agent at [SKILL.md](SKILL.md). Keep the `references/` and `scripts/` directories alongside it. You need an image generation tool, access to Tripo Studio, Blender, and Python 3.10 or later.

The deliverables are separately reviewed meshes and verification receipts. The workflow ends before character assembly and rigging.

[MIT License](LICENSE)
