import io
import struct
import zipfile

from app.services import attachments, mesh_convert


def make_card(client):
    p = client.post("/api/projects", json={"name": "Shop"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "Bracket"}).json()
    return card


def upload(client, card_id, name, data):
    return client.post(
        f"/api/cards/{card_id}/attachments",
        files={"file": (name, io.BytesIO(data), "application/octet-stream")},
    ).json()


THREEMF_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
 <resources>
  <object id="1" type="model">
   <mesh>
    <vertices>
     <vertex x="0" y="0" z="0"/><vertex x="10" y="0" z="0"/>
     <vertex x="0" y="10" z="0"/><vertex x="0" y="0" z="10"/>
    </vertices>
    <triangles>
     <triangle v1="0" v2="1" v3="2"/><triangle v1="0" v2="1" v3="3"/>
    </triangles>
   </mesh>
  </object>
 </resources>
 <build><item objectid="1" transform="1 0 0 0 1 0 0 0 1 5 0 0"/></build>
</model>"""


def make_3mf() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("3D/3dmodel.model", THREEMF_MODEL)
    return buf.getvalue()


def stl_triangle_count(data: bytes) -> int:
    return struct.unpack("<I", data[80:84])[0]


def test_3mf_converts_and_previews(client):
    card = make_card(client)
    att = upload(client, card["id"], "plate.3mf", make_3mf())
    pv = client.get(f"/api/attachments/{att['id']}/preview").json()
    assert pv["kind"] == "stl"
    assert pv["url"].endswith("/as-stl")
    assert pv["converted_from"] == "3mf"

    stl = client.get(pv["url"])
    assert stl.status_code == 200
    assert stl_triangle_count(stl.content) == 2
    # The build transform moved X by +5.
    first_vertex_x = struct.unpack("<3f", stl.content[84 + 12 : 84 + 24])[0]
    assert first_vertex_x == 5.0
    # Cached second fetch matches.
    assert client.get(pv["url"]).content == stl.content


def test_obj_converts_with_quad_fan(client):
    card = make_card(client)
    obj = b"v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1/1 2/2 3/3 4/4\n"
    att = upload(client, card["id"], "part.obj", obj)
    stl = client.get(f"/api/attachments/{att['id']}/as-stl")
    assert stl.status_code == 200
    assert stl_triangle_count(stl.content) == 2  # quad fan-triangulated


def test_convert_rejects_garbage(client):
    card = make_card(client)
    att = upload(client, card["id"], "junk.3mf", b"not a zip at all")
    assert client.get(f"/api/attachments/{att['id']}/as-stl").status_code == 422
    txt = upload(client, card["id"], "notes.txt", b"hello")
    assert client.get(f"/api/attachments/{txt['id']}/as-stl").status_code == 422


def test_zip_preview_lists_contents(client):
    card = make_card(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("firmware/main.bin", b"x" * 100)
        z.writestr("README.md", b"docs")
    att = upload(client, card["id"], "release.zip", buf.getvalue())
    pv = client.get(f"/api/attachments/{att['id']}/preview").json()
    assert pv["kind"] == "table"
    assert pv["columns"][0] == "file"
    names = [r[0] for r in pv["rows"]]
    assert "firmware/main.bin" in names and "README.md" in names


def test_media_and_iges_kinds(client):
    card = make_card(client)
    cases = {
        "clip.mp4": ("video", None),
        "walkthrough.mov": ("video", None),
        "note.mp3": ("audio", None),
        "housing.iges": ("step", "iges"),
        "housing.igs": ("step", "iges"),
        "bracket.step": ("step", "step"),
    }
    for name, (kind, fmt) in cases.items():
        att = upload(client, card["id"], name, b"x" * 10)
        pv = client.get(f"/api/attachments/{att['id']}/preview").json()
        assert pv["kind"] == kind, name
        if fmt:
            assert pv["format"] == fmt, name


def test_solidworks_with_embedded_preview(client, monkeypatch):
    card = make_card(client)
    att = upload(client, card["id"], "mount.sldprt", b"fake solidworks bytes")

    # No preview extractable: honest note.
    pv = client.get(f"/api/attachments/{att['id']}/preview").json()
    assert pv["kind"] == "model-unsupported"
    assert "no embedded preview" in pv["note"].lower()
    assert client.get(
        f"/api/attachments/{att['id']}/embedded-preview"
    ).status_code == 404

    # With an extractable thumbnail: image preview via the embedded route.
    png = b"\x89PNG\r\n\x1a\nfakepngdata"
    monkeypatch.setattr(
        mesh_convert, "extract_embedded_preview", lambda p: (png, "image/png")
    )
    pv = client.get(f"/api/attachments/{att['id']}/preview").json()
    assert pv["kind"] == "image"
    assert pv["url"].endswith("/embedded-preview")
    assert "preview image saved" in pv["note"]
    got = client.get(f"/api/attachments/{att['id']}/embedded-preview")
    assert got.status_code == 200
    assert got.content == png
    assert got.headers["content-type"] == "image/png"


def test_extractor_handles_non_ole_files(tmp_path):
    junk = tmp_path / "fake.sldprt"
    junk.write_bytes(b"definitely not an ole compound document")
    assert mesh_convert.extract_solidworks_preview(junk) is None


def test_pdf_still_previews(client):
    card = make_card(client)
    att = upload(client, card["id"], "drawing.pdf", b"%PDF-1.4 fake")
    pv = client.get(f"/api/attachments/{att['id']}/preview").json()
    assert pv["kind"] == "pdf"
    assert pv["url"].endswith("/file")


# ---- embedded preview extraction internals ----

def make_dib(width=2, height=2):
    import struct
    stride = ((width * 24 + 31) // 32) * 4
    pixels = b"\x00\x40\xff" * width + b"\x00" * (stride - 3 * width)
    header = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0,
                         stride * height, 2835, 2835, 0, 0)
    return header + pixels * height


def test_dib_to_bmp_roundtrip():
    bmp = mesh_convert._dib_to_bmp(make_dib())
    assert bmp is not None and bmp.startswith(b"BM")
    assert mesh_convert._dib_to_bmp(b"garbage") is None


def test_image_from_bytes_variants():
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 50
    assert mesh_convert._image_from_bytes(b"junk" + png)[1] == "image/png"
    wmf_with_dib = b"\x01\x00\x09\x00" + b"\x00" * 20 + make_dib()
    got = mesh_convert._image_from_bytes(wmf_with_dib)
    assert got is not None and got[1] == "image/bmp"
    assert mesh_convert._image_from_bytes(b"nothing here") is None


def test_scan_prefers_hinted_then_largest():
    png_small = b"\x89PNG\r\n\x1a\n" + b"a" * 10
    png_big = b"\x89PNG\r\n\x1a\n" + b"b" * 500
    got = mesh_convert.scan_streams_for_preview(
        [("random-stream", png_big), ("PreviewPNG", png_small)]
    )
    assert got[0] == png_small  # the hinted stream wins even when smaller
    got = mesh_convert.scan_streams_for_preview(
        [("a", png_small), ("b", png_big)]
    )
    assert got[0] == png_big


def test_vsdx_thumbnail_preview(client):
    card = make_card(client)
    png = b"\x89PNG\r\n\x1a\n" + b"visio-thumb" * 20
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("docProps/thumbnail.png", png)
        z.writestr("visio/pages/page1.xml", "<xml/>")
    att = upload(client, card["id"], "flow.vsdx", buf.getvalue())
    pv = client.get(f"/api/attachments/{att['id']}/preview").json()
    assert pv["kind"] == "image"
    assert "Visio" in pv["note"]
    got = client.get(f"/api/attachments/{att['id']}/embedded-preview")
    assert got.status_code == 200 and got.content == png


def test_illustrator_pdf_compatible(client):
    card = make_card(client)
    ai = b"%!PS-Adobe header junk %PDF-1.6 rest of pdf body"
    att = upload(client, card["id"], "logo.ai", ai)
    pv = client.get(f"/api/attachments/{att['id']}/preview").json()
    assert pv["kind"] == "pdf"
    got = client.get(pv["url"])
    assert got.headers["content-type"].startswith("application/pdf")

    plain = upload(client, card["id"], "old.ai", b"no pdf marker here")
    pv = client.get(f"/api/attachments/{plain['id']}/preview").json()
    assert pv["kind"] == "binary"
    assert "PDF compatibility" in pv["note"]


def test_diptrace_note(client):
    card = make_card(client)
    att = upload(client, card["id"], "board.dip", b"\x00" * 30)
    pv = client.get(f"/api/attachments/{att['id']}/preview").json()
    assert pv["kind"] == "model-unsupported"
    assert "Gerber" in pv["note"]
