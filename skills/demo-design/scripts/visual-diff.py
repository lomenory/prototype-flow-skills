#!/usr/bin/env python3
"""Dependency-free PNG visual comparison for demo-design viewport evidence."""

from __future__ import annotations

import argparse
import binascii
import json
import math
import struct
import zlib
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PNGError(ValueError):
    pass


def _paeth(a: int, b: int, c: int) -> int:
    value = a + b - c
    pa = abs(value - a)
    pb = abs(value - b)
    pc = abs(value - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_png(path: str | Path) -> tuple[int, int, bytes]:
    data = Path(path).read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise PNGError("not a PNG file")
    offset = len(PNG_SIGNATURE)
    width = height = color_type = bit_depth = interlace = None
    payload = bytearray()
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
            if compression != 0 or filtering != 0:
                raise PNGError("unsupported PNG compression or filter method")
        elif chunk_type == b"IDAT":
            payload.extend(chunk)
        elif chunk_type == b"IEND":
            break
    if not width or not height:
        raise PNGError("PNG is missing IHDR")
    if bit_depth != 8 or interlace != 0 or color_type not in {0, 2, 4, 6}:
        raise PNGError("only non-interlaced 8-bit grayscale/RGB/RGBA PNG is supported")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    row_bytes = width * channels
    try:
        raw = zlib.decompress(bytes(payload))
    except zlib.error as error:
        raise PNGError(f"invalid PNG data: {error}") from error
    expected = height * (row_bytes + 1)
    if len(raw) != expected:
        raise PNGError(f"unexpected PNG payload length: {len(raw)} != {expected}")
    rows: list[bytes] = []
    previous = bytes(row_bytes)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        encoded = raw[cursor : cursor + row_bytes]
        cursor += row_bytes
        decoded = bytearray(row_bytes)
        for index, value in enumerate(encoded):
            left = decoded[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                result = value
            elif filter_type == 1:
                result = value + left
            elif filter_type == 2:
                result = value + above
            elif filter_type == 3:
                result = value + ((left + above) // 2)
            elif filter_type == 4:
                result = value + _paeth(left, above, upper_left)
            else:
                raise PNGError(f"unsupported PNG filter: {filter_type}")
            decoded[index] = result & 0xFF
        previous = bytes(decoded)
        rows.append(previous)
    rgba = bytearray()
    for row in rows:
        for index in range(0, len(row), channels):
            if color_type == 0:
                gray = row[index]
                rgba.extend((gray, gray, gray, 255))
            elif color_type == 2:
                rgba.extend((row[index], row[index + 1], row[index + 2], 255))
            elif color_type == 4:
                gray, alpha = row[index], row[index + 1]
                rgba.extend((gray, gray, gray, alpha))
            else:
                rgba.extend(row[index : index + 4])
    return width, height, bytes(rgba)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png(path: str | Path, width: int, height: int, rgba: bytes) -> None:
    if len(rgba) != width * height * 4:
        raise PNGError("RGBA byte length does not match image dimensions")
    rows = b"".join(
        b"\x00" + rgba[row * width * 4 : (row + 1) * width * 4]
        for row in range(height)
    )
    payload = (
        PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(rows, level=9))
        + _chunk(b"IEND", b"")
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def _pixel_region(
    value: dict | None,
    image_width: int,
    image_height: int,
    label: str,
) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise PNGError(f"{label} must be an object")
    numbers = []
    for field in ("x", "y", "width", "height"):
        number = value.get(field)
        if (
            not isinstance(number, (int, float))
            or isinstance(number, bool)
            or not math.isfinite(number)
        ):
            raise PNGError(f"{label}.{field} must be finite")
        numbers.append(float(number))
    x, y, width, height = numbers
    if width <= 0 or height <= 0:
        raise PNGError(f"{label} width and height must be positive")
    left = max(0, math.floor(x))
    top = max(0, math.floor(y))
    right = min(image_width, math.ceil(x + width))
    bottom = min(image_height, math.ceil(y + height))
    if left >= right or top >= bottom:
        raise PNGError(f"{label} is outside the image")
    return {
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
    }


def _contains(region: dict, x: int, y: int) -> bool:
    return (
        region["x"] <= x < region["x"] + region["width"]
        and region["y"] <= y < region["y"] + region["height"]
    )


def compare_png(
    reference_path: str | Path,
    actual_path: str | Path,
    diff_path: str | Path | None = None,
    channel_threshold: int = 16,
    max_mismatch_ratio: float = 0.01,
    compare_region: dict | None = None,
    ignore_regions: list[dict] | None = None,
) -> dict:
    if channel_threshold < 0 or channel_threshold > 255:
        raise PNGError("channel_threshold must be between 0 and 255")
    if max_mismatch_ratio < 0 or max_mismatch_ratio > 1:
        raise PNGError("max_mismatch_ratio must be between 0 and 1")
    ref_width, ref_height, reference = read_png(reference_path)
    actual_width, actual_height, actual = read_png(actual_path)
    if (ref_width, ref_height) != (actual_width, actual_height):
        return {
            "status": "failed",
            "reason": "dimension_mismatch",
            "referenceSize": {"width": ref_width, "height": ref_height},
            "actualSize": {"width": actual_width, "height": actual_height},
            "mismatchRatio": 1.0,
            "maxMismatchRatio": max_mismatch_ratio,
            "channelThreshold": channel_threshold,
            "diffPath": None,
        }
    normalized_compare_region = _pixel_region(
        compare_region,
        ref_width,
        ref_height,
        "compare_region",
    )
    normalized_ignore_regions = [
        _pixel_region(region, ref_width, ref_height, f"ignore_regions[{index}]")
        for index, region in enumerate(ignore_regions or [])
    ]
    mismatches = 0
    total_delta = 0
    compared_pixels = 0
    excluded_pixels = 0
    diff = bytearray()
    for index in range(0, len(reference), 4):
        pixel_index = index // 4
        x = pixel_index % ref_width
        y = pixel_index // ref_width
        ref_pixel = reference[index : index + 4]
        actual_pixel = actual[index : index + 4]
        included = (
            normalized_compare_region is None
            or _contains(normalized_compare_region, x, y)
        ) and not any(
            _contains(region, x, y)
            for region in normalized_ignore_regions
            if region is not None
        )
        if not included:
            excluded_pixels += 1
            gray = sum(actual_pixel[:3]) // 3
            diff.extend((gray, gray, gray, 48))
            continue
        compared_pixels += 1
        deltas = [abs(ref_pixel[channel] - actual_pixel[channel]) for channel in range(4)]
        mismatch = max(deltas) > channel_threshold
        if mismatch:
            mismatches += 1
            diff.extend((255, 32, 32, 255))
        else:
            gray = sum(actual_pixel[:3]) // 3
            diff.extend((gray, gray, gray, 96))
        total_delta += sum(deltas)
    if compared_pixels == 0:
        raise PNGError("comparison region and masks exclude all pixels")
    pixel_count = ref_width * ref_height
    mismatch_ratio = mismatches / compared_pixels
    written_diff = None
    if diff_path is not None:
        write_png(diff_path, ref_width, ref_height, bytes(diff))
        written_diff = str(Path(diff_path))
    return {
        "status": "passed" if mismatch_ratio <= max_mismatch_ratio else "failed",
        "reason": None,
        "referenceSize": {"width": ref_width, "height": ref_height},
        "actualSize": {"width": actual_width, "height": actual_height},
        "mismatchedPixels": mismatches,
        "pixelCount": compared_pixels,
        "totalPixelCount": pixel_count,
        "excludedPixels": excluded_pixels,
        "mismatchRatio": mismatch_ratio,
        "meanChannelDelta": total_delta / (compared_pixels * 4),
        "maxMismatchRatio": max_mismatch_ratio,
        "channelThreshold": channel_threshold,
        "compareRegion": normalized_compare_region,
        "ignoreRegions": normalized_ignore_regions,
        "diffPath": written_diff,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare same-size PNG viewport screenshots")
    parser.add_argument("reference")
    parser.add_argument("actual")
    parser.add_argument("--diff")
    parser.add_argument("--channel-threshold", type=int, default=16)
    parser.add_argument("--max-mismatch-ratio", type=float, default=0.01)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args(argv)
    try:
        report = compare_png(
            args.reference,
            args.actual,
            args.diff,
            args.channel_threshold,
            args.max_mismatch_ratio,
        )
    except (OSError, PNGError) as error:
        report = {"status": "error", "reason": str(error)}
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
