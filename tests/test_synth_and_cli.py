import json

import numpy as np
import pytest

from acousticfem import cli, physics, synth


def test_transfer_function_peaks_at_the_mode():
    f = np.linspace(40, 60, 2001)
    H = synth.transfer_function(f, [50.0], [2.0], np.array([1.0]), np.array([1.0]))
    assert f[np.argmax(np.abs(H))] == pytest.approx(50.0, abs=0.02)


def test_free_decay_reaches_minus_60_db_at_t60():
    delta = 4.0
    T = physics.t60_from_decay(delta)
    envelope = lambda t: abs(synth.free_decay(t, np.array([[1.0]]), [0.0], [delta], np.array([1.0]))[0])
    assert 20 * np.log10(envelope(T) / envelope(0.0)) == pytest.approx(-60)


def test_impulse_response_is_normalized_audio():
    h = synth.impulse_response(0.5, 8000, [40.0, 70.0], [3.0, 5.0], np.array([1.0, 0.5]), np.array([0.8, -1.0]))
    assert len(h) == 4000 and np.abs(h).max() == pytest.approx(1.0)


def test_cli_box(tmp_path):
    out = tmp_path / "box"
    assert cli.main(["--box", "4", "3", "2.5", "--fmax", "80", "-o", str(out), "--grid", "0.5",
                     "--material", "floor=wood_floor", "--material", "ceiling=0.1",
                     "--material", "x0=0.05", "--material", "x1=0.05",
                     "--material", "y0=0.05", "--material", "y1=0.05"]) == 0
    for name in ("summary.json", "modes.csv", "modes.npz", "grid.npz", "spectrum.html",
                 "gallery.html", "impulse_response.wav"):
        assert (out / name).exists(), name
    summary = json.loads((out / "summary.json").read_text())
    assert summary["statistics"]["volume_m3"] == pytest.approx(30)
    grid = synth.load(out / "grid.npz")
    assert grid["shapes"].shape[:3] == grid["inside"].shape
    assert grid["shapes"].shape[3] == summary["modes"]["count"]


def test_cli_rejects_source_outside(tmp_path, capsys):
    assert cli.main(["--box", "4", "3", "2.5", "--fmax", "60", "--source", "9", "1", "1",
                     "-o", str(tmp_path), "--no-plots"]) == 1
    assert "outside the room" in capsys.readouterr().err
