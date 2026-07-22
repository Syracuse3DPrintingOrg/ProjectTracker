"""Convert open mesh formats to binary STL for the in-browser viewer.

3MF is a zip holding 3D/3dmodel.model (XML vertices and triangles); OBJ
is plain text v/f lines. Both convert to a triangle soup and come back
out as binary STL, which the existing viewer already renders. Converted
files are cached beside the original attachment.
"""

import re
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree

TRIANGLE_CAP = 2_000_000


class ConvertError(Exception):
    pass


def _stl_bytes(triangles: list[tuple]) -> bytes:
    """triangles: [((x,y,z), (x,y,z), (x,y,z)), ...] -> binary STL."""
    if not triangles:
        raise ConvertError("the file contains no triangles")
    if len(triangles) > TRIANGLE_CAP:
        raise ConvertError("the mesh is too large to preview; open it in a slicer")
    out = bytearray(b"\0" * 80)
    out += struct.pack("<I", len(triangles))
    for a, b, c in triangles:
        out += struct.pack("<3f", 0.0, 0.0, 0.0)  # viewer recomputes normals
        for v in (a, b, c):
            out += struct.pack("<3f", *v)
        out += b"\0\0"
    return bytes(out)


def threemf_to_stl(path: Path) -> bytes:
    """All mesh objects in a 3MF, merged. Build-item transforms are
    applied when present so multi-part plates land where they should."""
    try:
        with zipfile.ZipFile(path) as z:
            model_name = next(
                (n for n in z.namelist() if n.lower().endswith("3dmodel.model")),
                None,
            )
            if not model_name:
                raise ConvertError("no 3D model inside this 3MF")
            root = ElementTree.fromstring(z.read(model_name))
    except (zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ConvertError(f"could not read the 3MF: {exc}")

    ns = {"m": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {"m": ""}

    def q(tag):
        return f"{{{ns['m']}}}{tag}" if ns["m"] else tag

    meshes: dict[str, list[tuple]] = {}
    for obj in root.iter(q("object")):
        mesh = obj.find(q("mesh"))
        if mesh is None:
            continue
        verts = [
            (
                float(v.get("x", 0)),
                float(v.get("y", 0)),
                float(v.get("z", 0)),
            )
            for v in mesh.find(q("vertices")).iter(q("vertex"))
        ]
        tris = []
        for t in mesh.find(q("triangles")).iter(q("triangle")):
            try:
                tris.append(
                    (
                        verts[int(t.get("v1"))],
                        verts[int(t.get("v2"))],
                        verts[int(t.get("v3"))],
                    )
                )
            except (IndexError, TypeError, ValueError):
                continue
        meshes[obj.get("id", "")] = tris

    def transform(tri, matrix):
        if not matrix:
            return tri
        m = matrix
        def apply(v):
            x, y, z = v
            return (
                m[0] * x + m[3] * y + m[6] * z + m[9],
                m[1] * x + m[4] * y + m[7] * z + m[10],
                m[2] * x + m[5] * y + m[8] * z + m[11],
            )
        return tuple(apply(v) for v in tri)

    triangles: list[tuple] = []
    build = root.find(q("build"))
    items = list(build.iter(q("item"))) if build is not None else []
    if items:
        for item in items:
            tris = meshes.get(item.get("objectid", ""), [])
            matrix = None
            if item.get("transform"):
                try:
                    matrix = [float(x) for x in item.get("transform").split()]
                    if len(matrix) != 12:
                        matrix = None
                except ValueError:
                    matrix = None
            triangles.extend(transform(t, matrix) for t in tris)
    else:
        for tris in meshes.values():
            triangles.extend(tris)
    return _stl_bytes(triangles)


def obj_to_stl(path: Path) -> bytes:
    """Vertices and faces from an OBJ; polygon faces are fan-triangulated."""
    verts: list[tuple] = []
    triangles: list[tuple] = []
    try:
        text = path.read_text(errors="replace")
    except OSError as exc:
        raise ConvertError(str(exc))
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "v" and len(parts) >= 4:
            try:
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError:
                continue
        elif parts[0] == "f" and len(parts) >= 4:
            idx = []
            for token in parts[1:]:
                ref = token.split("/")[0]
                try:
                    i = int(ref)
                except ValueError:
                    idx = []
                    break
                idx.append(i - 1 if i > 0 else len(verts) + i)
            if len(idx) < 3:
                continue
            try:
                for k in range(1, len(idx) - 1):
                    triangles.append((verts[idx[0]], verts[idx[k]], verts[idx[k + 1]]))
            except IndexError:
                continue
    return _stl_bytes(triangles)


def extract_solidworks_preview(path: Path) -> tuple[bytes, str] | None:
    """The preview image SolidWorks embeds in its OLE container, as
    (bytes, mime). None when there is nothing usable to show."""
    import olefile

    try:
        if not olefile.isOleFile(str(path)):
            return None
        ole = olefile.OleFileIO(str(path))
    except OSError:
        return None
    try:
        candidates = sorted(
            (s for s in ole.listdir(streams=True, storages=False)),
            key=lambda s: ("png" not in s[-1].lower(), len(s)),
        )
        for stream in candidates:
            name = stream[-1].lower()
            if "preview" not in name and "thumbnail" not in name:
                continue
            data = ole.openstream(stream).read()
            if data.startswith(b"\x89PNG"):
                return data, "image/png"
            if data.startswith(b"BM"):
                return data, "image/bmp"
            # Some versions wrap the PNG a little way in; find it.
            pos = data.find(b"\x89PNG")
            if pos != -1:
                return data[pos:], "image/png"
        return None
    finally:
        ole.close()
