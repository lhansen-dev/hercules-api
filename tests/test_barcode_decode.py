import base64
import io

import pytest
from barcode import EAN13
from barcode.writer import ImageWriter

from hercules_api.services.barcode_decode import BarcodeDecodeError, decode_barcode_from_base64


def _make_ean13_png_base64(barcode: str) -> str:
    buf = io.BytesIO()
    EAN13(barcode, writer=ImageWriter()).write(buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_decode_ean13_barcode_roundtrip() -> None:
    # 12 digits; the library appends the checksum.
    b64 = _make_ean13_png_base64("012345678905")
    decoded = decode_barcode_from_base64(b64)
    assert decoded.startswith("012345678905")


def test_decode_rejects_invalid_base64() -> None:
    with pytest.raises(BarcodeDecodeError):
        decode_barcode_from_base64("not!!!base64$$$")


def test_decode_rejects_non_image_bytes() -> None:
    b64 = base64.b64encode(b"hello world, not an image").decode("ascii")
    with pytest.raises(BarcodeDecodeError):
        decode_barcode_from_base64(b64)
