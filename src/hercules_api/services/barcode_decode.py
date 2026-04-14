"""Deterministic barcode decoding from an image. Never uses a vision model."""

from __future__ import annotations

import base64
import binascii
import io

from PIL import Image, UnidentifiedImageError
from pyzbar.pyzbar import decode as zbar_decode


class BarcodeDecodeError(ValueError):
    """Image could not be decoded or contained no recognizable barcode."""


def decode_barcode_from_base64(image_b64: str) -> str:
    try:
        raw = base64.b64decode(image_b64, validate=False)
    except (binascii.Error, ValueError) as e:
        raise BarcodeDecodeError(f"Invalid base64 input: {e}") from e

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError) as e:
        raise BarcodeDecodeError(f"Could not open image: {e}") from e

    decoded = zbar_decode(image)
    if not decoded:
        raise BarcodeDecodeError("No barcode found in image.")

    # Pick the first UPC/EAN-style result; these are what Open Food Facts indexes.
    for d in decoded:
        kind = (d.type or "").upper()
        if kind in {"EAN13", "EAN8", "UPCA", "UPCE"}:
            return d.data.decode("ascii", errors="strict")

    # Fall back to whatever was first.
    return decoded[0].data.decode("ascii", errors="strict")
