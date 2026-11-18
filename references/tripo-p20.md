---
name: tripo-p20-public
description: Generate Hair, Head or Body meshes in Tripo Studio from a front image using multiview and the P2.0 Smart Mesh quad route. Use for the public three-part workflow.
---

# Tripo Studio P2.0 Smart Mesh

1. Open Tripo Studio in an available browser and use a signed-in session. If necessary, let the user sign in through the normal web flow. No specific browser or browser-control integration is required.
2. Work on one part at a time. In the **single-view** input, upload the accepted front image for Hair, Head or Body from the shared Master. Verify the preview, then click **Generate Multiview** when the button appears. Wait for that job and inspect the views for correct orientation, consistent shape and no extra parts. Verify the model task uses those views.
3. Select **Smart Mesh → P2.0**, **Quads**, and **25,000** target faces. Read back the selections and displayed cost before submission. If the required settings are unavailable, report the discrepancy; do not silently switch to the legacy high-poly route.
4. Record the input hash, settings, credit balance and cost as SUBMISSION_PENDING. Submit model generation once, then verify the task ID, asset list or credit change before considering any retry.
5. Inspect the returned mesh from front, sides, rear and oblique angles. Check part-specific details and verify the actual output topology after export. If quads matter, verify a quad-preserving export rather than judging the source from a triangulated GLB. A 25,000 target is not a guarantee of the exact exported face count.
6. **For Hair, inspect the exported hair alone**, using front, front-low and underside views with solid shading as well as its original material. Compare the shape of the front opening with the accepted Hair reference. If the mesh has a sheet or lock across a region shown open in the reference, record a source mismatch and return that part for repair before production assembly. A low view may legitimately see the back wall through the opening; rotate to confirm which surface spans the opening. Keep deliberate fringe coverage where it agrees with the reference. Do not infer a defect from eye visibility or try to clear eyes by lifting the entire hair part. An isolated face-opening mismatch remains an intake failure even if the assembly operator finishes.

P2.0 directly produces the low-poly mesh; there is no Retopology stage in this route. The generated head is new geometry and does not inherit the standard head's expression keys. Standard-head texture-only personalization is a separate workflow.
