---
name: tripo-to-blender-workflow
description: Generate separate Hair, Head, and Body assets with Image Gen and Tripo Studio P2.0, then review, repair, and manually assemble them in Blender with seam and skin-tone checks.
---

# Tripo to Blender workflow

Deliver one reviewed Blender assembly with separate Hair, Head, and Body objects, their source hashes, and an acceptance record. Use an image generation tool, a signed-in Tripo Studio web session, Blender with GLB support, and Python 3.10 or later for download intake. Stop after step 4 when the user only needs independent parts.

## 1. Generate references

Use [the image pipeline manifest](references/image-pipeline.json). Start with the user's original image or create one from their description. Generate a front-facing Master with shadows and baked lighting removed, then generate Hair, Head, and Body independently from that same Master. Preserve design details, colors, and deliberate asymmetry. Pass a single front image per part. Check the body is headless, in a T-pose, with palms facing down and separated fingers.

## 2. Generate and review in Tripo

Follow the [P2.0 web procedure](references/tripo-p20.md). Run three independent jobs, one each for Hair, Head, and Body. Generate multiviews from each front image and check them before submitting Smart Mesh P2.0 with Quads and 25,000 target faces. Record the pending submission and confirm the job before retrying. Review the returned mesh in multiple views and confirm the export format and actual topology.

## 3. Verify downloads and inspect in Blender

Use one confirmed local download per part. Baseline the download directory before exporting when an explicit file path will be unavailable. Use the download helper to reject ambiguous candidates and write a SHA-256 receipt. Run from the skill repository root, then use the exact accepted path for Blender import.

```sh
python scripts/tripo_ui_download_intake.py intake --candidate "/path/to/download.glb" --destination outputs/Hair.glb --receipt outputs/Hair-intake.json
```

Keep one working Blender file when a scene is needed. Identify the intended file and scene before making edits. Keep original imports available and record views and receipts instead of making a new working file at every gate.

Inspect each part alone from front, sides, back and oblique views, with both solid and original material views. Check missing geometry, face orientation, surface intersections, and texture defects separately. Inspect hair from the front, front-low and underside. Compare the opening, hairline, and deliberate fringe coverage with the reference. Recheck ambiguous areas while rotating to distinguish a hole from a glimpse of a rear surface. Record the defect, asset and view.

## 4. Repair confirmed defects and recheck

For suspected reversed faces, call the independent normal repair tool on one unrigged GLB at a time. Use a fresh Blender background process.

```sh
blender --background --factory-startup --python-exit-code 1 --python scripts/tripo_repair_normals.py -- --input outputs/Hair.glb --output outputs/Hair-repaired.glb
```

Read the `NORMAL_REPAIR` JSON line. A `repaired` result supplies a new candidate path and per-mesh face counts. `unchanged` uses the original asset. Omit `--output` for an audit. The detector uses visibility rays and can miss hidden faces or ambiguous open surfaces. Refresh Blender inspection after repair, compare the original material and Face Orientation at the same angles, and retain the candidate only if the defect is resolved. Keep rigged meshes and Shape Keys out of this tool.

For other defects, isolate the affected geometry before editing. Fix a small confirmed gap locally while retaining the intended silhouette and UVs. For fused or intersecting surfaces, inspect both sides before choosing the smallest repair. For a stain that survives neutral lighting and consistent normals, inspect the base-color image and UVs. Return the part for regeneration if a repair would change the design or cannot pass visual review.

## 5. Manually assemble and review in Blender

Follow [manual placement and 360-degree review](references/manual-assembly.md). The coding agent places the parts using Blender transforms, keeps the body fixed, and reviews the head/neck join before adding hair. Follow [skin-tone matching](references/skin-tone-match.md) if the head and body differ in base color. Review the assembled result in original materials and save the inspected pose with an interface verdict for each join. Keep the parts separate in the working file.
