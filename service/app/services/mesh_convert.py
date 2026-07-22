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


STREAM_SCAN_CAP = 30 * 1024 * 1024


def _dib_to_bmp(dib: bytes) -> bytes | None:
    """Wrap a raw DIB (BITMAPINFOHEADER + palette + pixels) into a BMP
    file browsers can render. None when the header does not add up."""
    if len(dib) < 40:
        return None
    bi_size, width, height = struct.unpack_from("<Iii", dib, 0)
    planes, bitcount = struct.unpack_from("<HH", dib, 12)
    compression, size_image = struct.unpack_from("<II", dib, 16)
    clr_used = struct.unpack_from("<I", dib, 32)[0]
    if not (
        bi_size >= 40
        and 0 < width <= 20000
        and 0 < abs(height) <= 20000
        and planes == 1
        and bitcount in (1, 4, 8, 16, 24, 32)
        and compression in (0, 3)
    ):
        return None
    palette = clr_used or (1 << bitcount if bitcount <= 8 else 0)
    offset = 14 + bi_size + palette * 4 + (12 if compression == 3 else 0)
    stride = ((width * bitcount + 31) // 32) * 4
    expected = offset - 14 + max(size_image, stride * abs(height))
    if len(dib) < expected:
        return None
    body = dib[:expected]
    header = b"BM" + struct.pack("<IHHI", 14 + len(body), 0, 0, offset)
    return header + body


def _image_from_bytes(data: bytes) -> tuple[bytes, str] | None:
    """Best renderable image inside a byte blob: PNG or JPEG anywhere,
    BMP at the front, or a DIB buried in a metafile."""
    pos = data.find(b"\x89PNG\r\n\x1a\n")
    if pos != -1:
        return data[pos:], "image/png"
    pos = data.find(b"\xff\xd8\xff")
    if pos != -1 and len(data) - pos > 100:
        return data[pos:], "image/jpeg"
    if data.startswith(b"BM"):
        return data, "image/bmp"
    # WMF/EMF thumbnails usually carry the raster as an embedded DIB.
    start = 0
    while True:
        pos = data.find(b"\x28\x00\x00\x00", start)
        if pos == -1:
            return None
        bmp = _dib_to_bmp(data[pos:])
        if bmp:
            return bmp, "image/bmp"
        start = pos + 4


def scan_streams_for_preview(streams) -> tuple[bytes, str] | None:
    """streams: iterable of (name, bytes). Name-hinted streams win, then
    anything with a recognizable image, largest first. Pure, testable."""
    hinted: list[tuple[bytes, str]] = []
    other: list[tuple[bytes, str]] = []
    for name, data in streams:
        if not data or len(data) > STREAM_SCAN_CAP:
            continue
        found = _image_from_bytes(data)
        if not found:
            continue
        lname = name.lower()
        target = hinted if ("preview" in lname or "thumbnail" in lname) else other
        target.append(found)
    for bucket in (hinted, other):
        if bucket:
            return max(bucket, key=lambda f: len(f[0]))
    return None


def _ole_thumbnail_property(ole) -> bytes | None:
    """The SummaryInformation thumbnail (property 17), the same image
    Windows Explorer renders for OLE documents."""
    try:
        props = ole.getproperties("\x05SummaryInformation")
    except Exception:
        return None
    blob = props.get(17)
    if isinstance(blob, bytes) and len(blob) > 8:
        # CLIPDATA: cbSize, cfFormat, then the payload (a METAFILEPICT
        # header precedes WMF bytes for CF_METAFILEPICT; DIB is raw).
        return blob
    return None


def extract_embedded_preview(path: Path) -> tuple[bytes, str] | None:
    """The preview image a document carries inside itself, whether the
    container is OLE (SolidWorks, old Visio, old Office) or a zip
    package (vsdx and friends). Mirrors what Windows Explorer shows."""
    import olefile

    try:
        if olefile.isOleFile(str(path)):
            ole = olefile.OleFileIO(str(path))
            try:
                def streams():
                    thumb = _ole_thumbnail_property(ole)
                    if thumb:
                        yield ("summary-thumbnail", thumb)
                    for entry in ole.listdir(streams=True, storages=False):
                        name = "/".join(entry)
                        try:
                            yield (name, ole.openstream(entry).read())
                        except OSError:
                            continue

                return scan_streams_for_preview(streams())
            finally:
                ole.close()
    except OSError:
        return None
    try:
        with zipfile.ZipFile(path) as z:
            def zstreams():
                names = z.namelist()
                ordered = sorted(
                    names,
                    key=lambda n: ("thumbnail" not in n.lower(), n),
                )
                for n in ordered[:50]:
                    info = z.getinfo(n)
                    if info.file_size > STREAM_SCAN_CAP or info.is_dir():
                        continue
                    if "thumbnail" in n.lower() or n.lower().startswith("docprops/"):
                        yield (n, z.read(n))

            return scan_streams_for_preview(zstreams())
    except (zipfile.BadZipFile, OSError):
        return None


# The old name stays callable; SolidWorks was the first user of this.
extract_solidworks_preview = extract_embedded_preview
