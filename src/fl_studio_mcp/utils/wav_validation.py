"""Bounded RIFF/WAVE structure and signal checks."""

from __future__ import annotations

import math
import struct
from pathlib import Path

_MAX_SAMPLES = 50_000_000
_MAX_CHUNKS = 4096
_PCM_BITS = {8, 16, 24, 32}
_FLOAT_BITS = {32, 64}


def _read_chunks(stream, file_size: int) -> tuple[bytes, tuple[int, int]]:
    header = stream.read(12)
    if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
        raise ValueError("Expected a RIFF/WAVE file")
    end = struct.unpack_from("<I", header, 4)[0] + 8
    if not 12 <= end <= file_size:
        raise ValueError("WAV is incomplete: invalid RIFF size")
    fmt = data = None
    for _ in range(_MAX_CHUNKS):
        if stream.tell() == end:
            break
        chunk_header = stream.read(min(8, end - stream.tell()))
        if len(chunk_header) != 8:
            raise ValueError("WAV is incomplete: truncated chunk header")
        kind, length = struct.unpack("<4sI", chunk_header)
        offset = stream.tell()
        chunk_end = offset + length
        if chunk_end > end:
            raise ValueError("WAV is incomplete: chunk exceeds RIFF")
        if kind == b"fmt ":
            if fmt is not None:
                raise ValueError("Multiple WAV format chunks")
            fmt = stream.read(min(length, 40))
        elif kind == b"data":
            if data is not None:
                raise ValueError("Multiple WAV data chunks are unsupported")
            data = (offset, length)
        # Some writers omit padding on a final odd-length data chunk.
        stream.seek(chunk_end + (length & 1) if chunk_end < end else chunk_end)
    if stream.tell() != end:
        raise ValueError("WAV contains too many chunks")
    if fmt is None or len(fmt) < 16 or data is None:
        raise ValueError("Missing WAV format or data chunk")
    return fmt, data


def _format(fmt: bytes) -> tuple[int, int, int, int, int, int]:
    encoding, channels, rate, byte_rate, align, bits = struct.unpack_from("<HHIIHH", fmt)
    valid_bits = bits
    if encoding == 0xFFFE:
        if (
            len(fmt) < 40
            or struct.unpack_from("<H", fmt, 16)[0] < 22
            or fmt[26:40] != bytes.fromhex("000000001000800000aa00389b71")
        ):
            raise ValueError("Unsupported extensible WAV format")
        valid_bits = struct.unpack_from("<H", fmt, 18)[0]
        encoding = struct.unpack_from("<H", fmt, 24)[0]
    if not (1 <= channels <= 64 and 1 <= rate <= 768_000):
        raise ValueError("Invalid WAV channel count or sample rate")
    if not (
        (encoding == 1 and bits in _PCM_BITS and 1 <= valid_bits <= bits)
        or (encoding == 3 and bits in _FLOAT_BITS and valid_bits == bits)
    ):
        raise ValueError("Only PCM and IEEE float WAV are supported")
    if align != channels * (bits // 8) or byte_rate != rate * align:
        raise ValueError("Invalid WAV frame alignment or byte rate")
    return encoding, channels, rate, align, bits, valid_bits


def _samples(chunk: bytes, encoding: int, bits: int):
    if encoding == 3:
        return (sample for (sample,) in struct.iter_unpack("<f" if bits == 32 else "<d", chunk))
    scale = 1 << (bits - 1)
    if bits == 8:
        return ((sample - 128) / scale for sample in chunk)
    if bits == 24:
        view = memoryview(chunk)
        return (
            int.from_bytes(view[offset : offset + 3], "little", signed=True) / scale
            for offset in range(0, len(chunk), 3)
        )
    return (sample / scale for (sample,) in struct.iter_unpack("<h" if bits == 16 else "<i", chunk))


def inspect_wav(
    path: str | Path, max_frames: int = 5_000_000, expected_duration: float | None = None
) -> dict:
    """Measure the file's duration and scan a bounded prefix of the audio frames."""
    path = Path(path).resolve(strict=True)
    if path.suffix.lower() != ".wav" or not path.is_file():
        raise ValueError("Expected an existing WAV file")
    if type(max_frames) is not int or not 1 <= max_frames <= _MAX_SAMPLES:
        raise ValueError("max_frames must be in 1..50000000")
    if expected_duration is not None and (
        type(expected_duration) not in (int, float) or not 0 < expected_duration < math.inf
    ):
        raise ValueError("expected_duration must be a positive finite number")
    with path.open("rb") as stream:
        stream.seek(0, 2)
        file_size = stream.tell()
        stream.seek(0)
        fmt, (data_offset, data_size) = _read_chunks(stream, file_size)
        encoding, channels, rate, align, bits, valid_bits = _format(fmt)
        if data_size % align:
            raise ValueError("WAV data contains an incomplete frame")
        frames = data_size // align
        checked = min(frames, max_frames, _MAX_SAMPLES // channels)
        stream.seek(data_offset)
        peak = [0.0] * channels
        sums = [0.0] * channels
        squares = [0.0] * channels
        finite_count = [0] * channels
        nonfinite = full_scale = 0
        positive_rail = 1 - 1 / (1 << (valid_bits - 1)) if encoding == 1 else 1.0
        for start in range(0, checked, 4096):
            size = min(4096, checked - start) * align
            chunk = stream.read(size)
            if len(chunk) != size:
                raise ValueError("WAV data was truncated during inspection")
            for index, value in enumerate(_samples(chunk, encoding, bits)):
                if not math.isfinite(value):
                    nonfinite += 1
                    continue
                channel = index % channels
                finite_count[channel] += 1
                magnitude = abs(value)
                full_scale += value >= positive_rail or value <= -1.0
                # Accumulate relative to the channel peak to avoid overflow on float WAV.
                scale = peak[channel]
                if magnitude > scale:
                    ratio = scale / magnitude
                    sums[channel] *= ratio
                    squares[channel] *= ratio * ratio
                    peak[channel] = scale = magnitude
                if scale:
                    relative = value / scale
                    sums[channel] += relative
                    squares[channel] += relative * relative

    duration = frames / rate
    duration_matches = expected_duration is None or abs(duration - expected_duration) <= 1 / rate
    non_silent = any(peak)
    complete = checked == frames
    return {
        "path": str(path),
        "sample_rate": rate,
        "channels": channels,
        "bits_per_sample": bits,
        "encoding": "PCM" if encoding == 1 else "IEEE_FLOAT",
        "frames": frames,
        "duration_seconds": duration,
        "duration_matches": duration_matches,
        "analyzed_frames": checked,
        "complete": complete,
        "peak": peak,
        "rms": [
            p * math.sqrt(min(1.0, square / count)) if count else 0.0
            for p, square, count in zip(peak, squares, finite_count)
        ],
        "dc_offset": [
            p * max(-1.0, min(1.0, total / count)) if count else 0.0
            for p, total, count in zip(peak, sums, finite_count)
        ],
        "nonfinite_samples": nonfinite,
        "full_scale_samples": full_scale,
        "non_silent": non_silent,
        "passed": complete and non_silent and not nonfinite and not full_scale and duration_matches,
    }
