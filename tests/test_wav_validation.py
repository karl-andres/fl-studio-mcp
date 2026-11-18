import math
import struct
import sys
import wave

import pytest

from fl_studio_mcp.utils.wav_validation import inspect_wav


def test_tone_reports_duration_rms_and_incomplete_scan(tmp_path):
    path = tmp_path / "render.wav"
    rate = 8000
    samples = [round(8192 * math.sin(2 * math.pi * 400 * n / rate)) for n in range(rate)]
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        stream.writeframes(struct.pack("<8000h", *samples))

    result = inspect_wav(path, expected_duration=1)
    assert result["passed"] and result["duration_seconds"] == 1
    assert result["rms"][0] == pytest.approx(0.25 / math.sqrt(2), abs=0.0001)
    assert not inspect_wav(path, expected_duration=1.1)["passed"]
    limited = inspect_wav(path, max_frames=100)
    assert limited["analyzed_frames"] == 100 and not limited["passed"]


def test_truncated_riff_is_rejected(tmp_path):
    path = tmp_path / "incomplete.wav"
    path.write_bytes(b"RIFF" + struct.pack("<I", 1000) + b"WAVE")
    with pytest.raises(ValueError, match="incomplete"):
        inspect_wav(path)


def test_float_render_never_passes_nonfinite_or_overrange_samples(tmp_path):
    path = tmp_path / "float.wav"
    fmt = struct.pack("<HHIIHH", 3, 1, 48000, 384000, 8, 64)
    samples = struct.pack("<4d", float("nan"), sys.float_info.max, -sys.float_info.max, 0.5)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"data" + struct.pack("<I", len(samples)) + samples
    path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks)
    result = inspect_wav(path)
    assert result["nonfinite_samples"] == 1
    assert result["full_scale_samples"] == 2
    assert math.isfinite(result["rms"][0])
    assert not result["passed"]


def test_pcm_full_scale_uses_separate_positive_and_negative_rails(tmp_path):
    path = tmp_path / "rails.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        stream.writeframes(struct.pack("<3h", -32767, 32767, -32768))
    assert inspect_wav(path)["full_scale_samples"] == 2
