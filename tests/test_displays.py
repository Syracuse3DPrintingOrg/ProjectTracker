import pytest

from app import config
from app.services import displays


def test_registry_crud(temp_data_dir):
    d = displays.create_display("Kitchen TV", "androidtv", adb_host="192.168.1.60")
    assert d["id"] and d["kind"] == "androidtv"

    assert displays.get_display(d["id"])["name"] == "Kitchen TV"
    displays.update_display(d["id"], name="Hall TV", params={"theme": "light", "junk": "x"})
    updated = displays.get_display(d["id"])
    assert updated["name"] == "Hall TV"
    assert updated["params"] == {"theme": "light"}  # unknown keys dropped

    assert displays.delete_display(d["id"]) is True
    assert displays.delete_display(d["id"]) is False
    assert displays.list_displays() == []


def test_create_rejects_unknown_kind(temp_data_dir):
    with pytest.raises(ValueError):
        displays.create_display("X", "smartfridge")


def test_display_url_includes_params_and_token(temp_data_dir):
    d = displays.create_display("Pi", "browser", params={"theme": "light", "scale": "1.25"})
    url = displays.display_url(d, "http://tracker.lan:9280/", {"password_hash": "", "display_token": ""})
    assert url.startswith("http://tracker.lan:9280/display?")
    assert f"d={d['id']}" in url
    assert "theme=light" in url and "scale=1.25" in url
    assert "token" not in url

    locked = {"password_hash": "x$y", "display_token": "sekrit"}
    assert "token=sekrit" in displays.display_url(d, "http://tracker.lan:9280", locked)
    assert displays.api_url(d, "http://tracker.lan:9280", locked).endswith("/api/display?token=sekrit")


def test_adb_command_building():
    cmds = displays.build_adb_commands("192.168.1.60", "show", "http://t/display?d=1")
    assert cmds[0] == ["adb", "connect", "192.168.1.60:5555"]
    assert cmds[1][-1] == "KEYCODE_WAKEUP"
    assert cmds[2][-1] == "http://t/display?d=1"
    assert "-s" in cmds[2] and "192.168.1.60:5555" in cmds[2]

    hide = displays.build_adb_commands("192.168.1.60:5037", "hide")
    assert hide[0] == ["adb", "connect", "192.168.1.60:5037"]  # explicit port kept
    assert hide[1][-1] == "KEYCODE_HOME"

    with pytest.raises(displays.AdbError):
        displays.build_adb_commands("", "show", "http://x")
    with pytest.raises(displays.AdbError):
        displays.build_adb_commands("192.168.1.60", "show", "")
    with pytest.raises(displays.AdbError):
        displays.build_adb_commands("192.168.1.60", "reboot")


def test_run_adb_reports_connect_failure(temp_data_dir, monkeypatch):
    class FakeProc:
        returncode = 0
        stdout = "failed to connect to 192.168.1.60:5555"
        stderr = ""

    monkeypatch.setattr(displays, "adb_available", lambda: True)
    monkeypatch.setattr(displays, "_run", lambda cmd: FakeProc())
    with pytest.raises(displays.AdbError):
        displays.run_adb("192.168.1.60", "hide")


def test_run_adb_success(temp_data_dir, monkeypatch):
    calls = []

    class FakeProc:
        returncode = 0
        stdout = "connected"
        stderr = ""

    monkeypatch.setattr(displays, "adb_available", lambda: True)
    monkeypatch.setattr(displays, "_run", lambda cmd: (calls.append(cmd), FakeProc())[1])
    result = displays.run_adb("192.168.1.60", "show", "http://t/display")
    assert result["ok"] is True
    assert len(calls) == 3


def test_displays_api(client, monkeypatch):
    resp = client.post(
        "/api/displays",
        json={"name": "Kitchen TV", "kind": "androidtv", "adb_host": "192.168.1.60",
              "params": {"theme": "contrast", "tv": "1"}},
    )
    assert resp.status_code == 201
    d = resp.json()
    assert "url" in d and f"d={d['id']}" in d["url"]

    assert client.post("/api/displays", json={"name": "X", "kind": "toaster"}).status_code == 422

    # TV action with mocked adb
    monkeypatch.setattr(displays, "run_adb", lambda host, action, url="": {"ok": True, "detail": ""})
    assert client.post(f"/api/displays/{d['id']}/tv/show").json()["ok"] is True
    assert client.post(f"/api/displays/{d['id']}/tv/reboot").status_code == 404

    browser = client.post("/api/displays", json={"name": "Pi", "kind": "browser"}).json()
    assert client.post(f"/api/displays/{browser['id']}/tv/show").status_code == 400

    assert client.delete(f"/api/displays/{d['id']}").status_code == 204
    assert client.delete(f"/api/displays/{d['id']}").status_code == 404


def test_display_page_uses_registered_params(client):
    d = client.post(
        "/api/displays",
        json={"name": "Hall", "kind": "browser",
              "params": {"theme": "light", "scale": "1.5", "tv": "1"}},
    ).json()
    page = client.get(f"/display?d={d['id']}").text
    assert "theme-light" in page and "tv" in page and "1.5" in page
    assert "Hall" in page

    # Query params override the registered look.
    page = client.get(f"/display?d={d['id']}&theme=contrast").text
    assert "theme-contrast" in page

    # Unregistered id still renders with defaults.
    assert client.get("/display?d=nope").status_code == 200


def test_displays_page_renders(client):
    client.post("/api/displays", json={"name": "Kitchen TV", "kind": "androidtv"})
    resp = client.get("/displays")
    assert resp.status_code == 200
    assert "Kitchen TV" in resp.text


def test_display_registry_survives_other_settings_saves(temp_data_dir):
    displays.create_display("Pi", "browser")
    config.save_settings({"app_title": "Boards"})
    assert len(displays.list_displays()) == 1
