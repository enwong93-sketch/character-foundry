"""Audit or repair face orientation in a Tripo GLB with Blender's Python."""

import argparse
import json
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def world_vertices(obj):
    coords = np.empty(3 * len(obj.data.vertices), dtype=np.float64)
    obj.data.vertices.foreach_get("co", coords)
    world = np.asarray(obj.matrix_world)
    return coords.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]


def inspect_faces(objects):
    """Adapt Auto Rig's outside visibility test for unrigged source parts."""
    points = []
    triangles = []
    offset = 0
    for obj in objects:
        obj.data.calc_loop_triangles()
        points.append(world_vertices(obj))
        triangles.extend([offset + i for i in tri.vertices] for tri in obj.data.loop_triangles)
        offset += len(obj.data.vertices)
    if not triangles:
        raise ValueError("Input contains no mesh faces")
    points = np.concatenate(points)
    size = float(np.ptp(points, axis=0).max())
    if not np.isfinite(size) or size <= 0:
        raise ValueError("Input has invalid mesh bounds")
    cast = BVHTree.FromPolygons(points.tolist(), triangles, all_triangles=True).ray_cast
    step, reach = 2e-5 * size, 2 * size
    indices = np.arange(26) + 0.5
    polar = np.arccos(1 - 2 * indices / len(indices))
    turn = np.pi * (1 + np.sqrt(5)) * indices
    directions = [Vector(d) for d in zip(np.cos(turn) * np.sin(polar),
                                         np.sin(turn) * np.sin(polar), np.cos(polar))]

    def visible(origin, direction):
        return cast(origin, direction, reach)[0] is None

    for obj in objects:
        world = obj.matrix_world
        linear = world.to_3x3()
        # Reflection changes world-space winding as well as the normal transform.
        normal_matrix = linear.inverted().transposed()
        orientation = -1 if linear.determinant() < 0 else 1
        reversed_faces = []
        two_sided_faces = 0
        for face in obj.data.polygons:
            normal = (normal_matrix @ face.normal).normalized() * orientation
            if not normal.length:
                continue
            center = world @ face.center
            if visible(center + step * normal, normal):
                two_sided_faces += int(visible(center - step * normal, -normal))
                continue
            back_hits = 0
            front_hit = False
            for direction in directions:
                facing = normal.dot(direction)
                if abs(facing) < 0.2:
                    continue
                side = 1 if facing > 0 else -1
                if not visible(center + step * (direction + side * normal), direction):
                    continue
                if side > 0:
                    front_hit = True
                else:
                    back_hits += 1
                if front_hit and back_hits:
                    break
            if back_hits >= 2 and not front_hit:
                reversed_faces.append(face.index)
            elif back_hits and front_hit:
                two_sided_faces += 1
        yield obj, reversed_faces, two_sided_faces


def reverse_faces(mesh, indices):
    if not indices:
        return
    custom = None
    if mesh.has_custom_normals:
        custom = {
            (face.index, mesh.loops[i].vertex_index): mesh.corner_normals[i].vector.copy()
            for face in mesh.polygons for i in face.loop_indices
        }
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.faces.ensure_lookup_table()
        bmesh.ops.reverse_faces(bm, faces=[bm.faces[i] for i in indices], flip_multires=True)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    if custom is not None:
        turned = set(indices)
        normals = [None] * len(mesh.loops)
        for face in mesh.polygons:
            for index in face.loop_indices:
                normal = custom[face.index, mesh.loops[index].vertex_index]
                if face.index in turned and normal.dot(face.normal) < 0:
                    normal = -normal
                normals[index] = normal
        mesh.normals_split_custom_set(normals)


def run(source, output=None):
    source = Path(source).resolve(strict=True)
    output = Path(output).resolve() if output is not None else None
    if source.suffix.lower() != ".glb":
        raise ValueError("Input must be a .glb file")
    if output is not None:
        if output.suffix.lower() != ".glb" or not output.parent.is_dir():
            raise ValueError("Output must be a .glb in an existing directory")
        if output.exists() or output == source:
            raise ValueError("Choose a new output path")
    before = set(bpy.context.scene.objects)
    if bpy.ops.import_scene.gltf(filepath=str(source)) != {"FINISHED"}:
        raise RuntimeError("GLB import failed")
    imported = sorted(set(bpy.context.scene.objects) - before, key=lambda obj: obj.name)
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if any(obj.type == "ARMATURE" for obj in imported) or any(
        obj.data.shape_keys or obj.vertex_groups for obj in meshes
    ):
        raise ValueError("Use unrigged GLB parts without shape keys")
    # Complete the inspection before changing winding, so every object shares one baseline.
    findings = list(inspect_faces(meshes))
    changed = sum(len(indices) for _, indices, _ in findings)
    if output is not None and changed:
        for obj, indices, _ in findings:
            if indices and obj.data.users > 1:
                obj.data = obj.data.copy()
            reverse_faces(obj.data, indices)
        bpy.ops.object.select_all(action="DESELECT")
        for obj in imported:
            obj.select_set(True)
        if bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB",
                                     use_selection=True) != {"FINISHED"}:
            raise RuntimeError("GLB export failed")
    return {
        "source": str(source),
        "status": "audited" if output is None else "repaired" if changed else "unchanged",
        "asset": str(output if output is not None and changed else source),
        "meshes": [
            {"name": obj.name, "faces_flagged": len(indices),
             "faces_reversed": len(indices) if output is not None else 0,
             "two_sided_faces": two_sided}
            for obj, indices, two_sided in findings
        ],
    }


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="New GLB written only if faces are repaired")
    args = parser.parse_args(argv)
    print("NORMAL_REPAIR " + json.dumps(run(args.input, args.output), ensure_ascii=True))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
