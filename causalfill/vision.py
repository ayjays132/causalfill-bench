"""Small, deterministic RGB raster observations for controlled perception tasks.

This is a scientific stimulus renderer, not a photorealistic engine.  The image
wire format contains only pixels and image integrity metadata.  Neither object
annotations nor a camera matrix are embedded in a PNG or its envelope.  The
scripted detector below operates on decoded pixels and supplied color/landmark
contracts; it has no access to a task object or its hidden state.

Coordinates refer to pixel centers: pixel (column, row) samples image position
(column + 0.5, row + 0.5).  The affine camera maps 2-D world coordinates to that
image coordinate frame.  Shapes are opaque and later shapes occlude earlier
ones.  This renderer has no depth, perspective, lighting model, or dynamics.
"""
from __future__ import annotations

import base64
import binascii
from collections import deque
import hashlib
import math
import random
import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_DIMENSION = 1024
MAX_PIXELS = 1024 * 1024
MAX_PNG_BYTES = 8 * 1024 * 1024
ENVELOPE_KEYS = frozenset({"mime_type", "width", "height", "png_base64", "sha256"})


def _integer(value, lower, upper, name):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in [{lower}, {upper}]")
    return value


def _number(value, name="coordinate"):
    if type(value) not in (int, float) or abs(value) > 1_000_000 or not math.isfinite(value):
        raise ValueError(f"{name} must be finite and have magnitude at most 1000000")
    return float(value)


def _point(value, length=2, name="point"):
    if type(value) not in (list, tuple) or len(value) != length:
        raise ValueError(f"{name} must contain {length} numbers")
    return [_number(x, name) for x in value]


def _color(rgb):
    if type(rgb) not in (list, tuple) or len(rgb) != 3:
        raise ValueError("rgb must contain three integers")
    return tuple(_integer(x, 0, 255, "color channel") for x in rgb)


def _dimensions(width, height):
    _integer(width, 1, MAX_DIMENSION, "width")
    _integer(height, 1, MAX_DIMENSION, "height")
    if width * height > MAX_PIXELS:
        raise ValueError("image exceeds the pixel cap")


def _chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload +
            struct.pack(">I", binascii.crc32(kind + payload) & 0xffffffff))


def encode_png(width: int, height: int, rgb: bytes) -> bytes:
    """Encode only RGB8, noninterlaced, filter-0 PNG, with no ancillary data."""
    _dimensions(width, height)
    if type(rgb) is not bytes or len(rgb) != width * height * 3:
        raise ValueError("RGB byte count does not match dimensions")
    stride = width * 3
    raw = b"".join(b"\x00" + rgb[y*stride:(y+1)*stride] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return PNG_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b"")


def decode_png(data: bytes) -> tuple[int, int, bytes]:
    """Strict bounded decoder for this module's PNG profile, not arbitrary PNG.

    Rejects metadata, extra trailing bytes, unsupported filters/color formats,
    CRC errors, dimensions outside the cap, overlong compressed/decompressed
    streams, and concatenated zlib streams.  An ordinary PNG viewer can open
    our output; this intentionally narrow reader does not accept every PNG.
    """
    if type(data) is not bytes or not len(PNG_SIGNATURE) <= len(data) <= MAX_PNG_BYTES:
        raise ValueError("invalid PNG byte length")
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("invalid PNG signature")
    pos = len(PNG_SIGNATURE)
    width = height = None
    payloads = []
    stage = 0
    chunks = 0
    while pos < len(data):
        if len(data) - pos < 12:
            raise ValueError("truncated PNG chunk")
        length = struct.unpack(">I", data[pos:pos+4])[0]
        kind = data[pos+4:pos+8]
        if length > MAX_PNG_BYTES or length > len(data) - pos - 12:
            raise ValueError("invalid PNG chunk size")
        payload = data[pos+8:pos+8+length]
        crc = struct.unpack(">I", data[pos+8+length:pos+12+length])[0]
        if crc != (binascii.crc32(kind + payload) & 0xffffffff):
            raise ValueError("PNG CRC mismatch")
        pos += 12 + length
        chunks += 1
        if chunks > 64:
            raise ValueError("too many PNG chunks")
        if kind == b"IHDR":
            if stage != 0 or length != 13:
                raise ValueError("PNG must begin with one IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            _dimensions(width, height)
            if (depth, color, compression, filtering, interlace) != (8, 2, 0, 0, 0):
                raise ValueError("unsupported PNG profile")
            stage = 1
        elif kind == b"IDAT":
            if stage not in (1, 2) or not payload:
                raise ValueError("invalid IDAT order or size")
            payloads.append(payload)
            stage = 2
        elif kind == b"IEND":
            if stage != 2 or length != 0 or pos != len(data):
                raise ValueError("invalid PNG end")
            stage = 3
        else:
            # A narrow wire format makes accidental hidden annotations visible.
            raise ValueError("ancillary or unknown PNG chunks are not permitted")
    if stage != 3 or width is None or height is None:
        raise ValueError("incomplete PNG")
    expected = height * (1 + width * 3)
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(b"".join(payloads), expected + 1)
    except zlib.error as exc:
        raise ValueError("invalid PNG compression") from exc
    if (len(raw) != expected or decoder.unconsumed_tail or decoder.unused_data or not decoder.eof):
        raise ValueError("PNG decompression size or stream mismatch")
    stride = width * 3
    rows = []
    for y in range(height):
        start = y * (stride + 1)
        if raw[start] != 0:
            raise ValueError("unsupported PNG scanline filter")
        rows.append(raw[start+1:start+1+stride])
    return width, height, b"".join(rows)


def image_envelope(png_bytes: bytes) -> dict:
    """Create the public image-only envelope after validating its PNG bytes."""
    width, height, _ = decode_png(png_bytes)
    return {"mime_type": "image/png", "width": width, "height": height,
            "png_base64": base64.b64encode(png_bytes).decode("ascii"),
            "sha256": hashlib.sha256(png_bytes).hexdigest()}


def decode_envelope(image: dict) -> tuple[int, int, bytes]:
    """Validate an exact image envelope, including dimensions and SHA256."""
    if type(image) is not dict or set(image) != ENVELOPE_KEYS or image["mime_type"] != "image/png":
        raise ValueError("invalid image envelope")
    _dimensions(image["width"], image["height"])
    text = image["png_base64"]
    if type(text) is not str or len(text) > 4*((MAX_PNG_BYTES+2)//3):
        raise ValueError("invalid image base64 size")
    sha = image["sha256"]
    if type(sha) is not str or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("invalid image digest")
    try:
        png = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid image base64") from exc
    if hashlib.sha256(png).hexdigest() != sha:
        raise ValueError("image digest mismatch")
    width, height, rgb = decode_png(png)
    if (width, height) != (image["width"], image["height"]):
        raise ValueError("image envelope dimensions mismatch")
    return width, height, rgb


def _matrix(matrix):
    if type(matrix) not in (list, tuple) or len(matrix) != 2:
        raise ValueError("camera matrix must be a 2 by 3 array")
    first, second = (_point(row, 3, "camera matrix row") for row in matrix)
    a, b, tx = first
    c, d, ty = second
    det = a*d - b*c
    if not math.isfinite(det) or abs(det) < 1e-9:
        raise ValueError("singular or numerically unsupported camera matrix")
    return first, second, det


def world_to_pixel(matrix, point):
    first, second, _ = _matrix(matrix)
    x, y = _point(point)
    return [first[0]*x+first[1]*y+first[2], second[0]*x+second[1]*y+second[2]]


def pixel_to_world(matrix, point):
    """Invert an observed/calibrated affine camera; no hidden geometry is used."""
    first, second, determinant = _matrix(matrix)
    u, v = _point(point)
    u -= first[2]
    v -= second[2]
    return [(second[1]*u-first[1]*v)/determinant,
            (first[0]*v-second[0]*u)/determinant]


def render_scene(shapes: list[dict], camera: dict, *, noise: int = 0,
                 noise_seed: int = 0, background=(235, 239, 244)) -> dict:
    """Rasterize opaque rectangles/circles, then add independent bounded RGB noise.

    Geometry is private input, never output metadata.  Noise is sampled for
    every pixel/channel regardless of objects, so a fully occluded object's
    geometry cannot change the noise pattern.  Repeated images with identical
    inputs are identical; repeated captures do not average away fresh noise.
    """
    if type(camera) is not dict or set(camera) != {"width", "height", "matrix"}:
        raise ValueError("camera requires width, height and matrix")
    width, height = camera["width"], camera["height"]
    _dimensions(width, height)
    first, second, determinant = _matrix(camera["matrix"])
    _integer(noise, 0, 32, "noise")
    _integer(noise_seed, 0, 2**63-1, "noise_seed")
    back = _color(background)
    if type(shapes) is not list or len(shapes) > 512:
        raise ValueError("shapes must be an array of at most 512 primitives")
    # Validate every primitive before writing pixels.
    clean = []
    for shape in shapes:
        if type(shape) is not dict:
            raise ValueError("invalid shape")
        kind = shape.get("shape")
        if kind == "rect" and set(shape) == {"shape", "bounds", "rgb"}:
            x0, y0, x1, y1 = _point(shape["bounds"], 4, "rectangle bounds")
            if x1 <= x0 or y1 <= y0:
                raise ValueError("rectangle bounds must have positive extent")
            geometry = (x0, y0, x1, y1)
        elif kind == "circle" and set(shape) == {"shape", "center", "radius", "rgb"}:
            cx, cy = _point(shape["center"], 2, "circle center")
            radius = _number(shape["radius"], "radius")
            if radius <= 0:
                raise ValueError("circle radius must be positive")
            x0, y0, x1, y1 = cx-radius, cy-radius, cx+radius, cy+radius
            geometry = (cx, cy, radius)
        else:
            raise ValueError("unsupported shape or fields")
        color = _color(shape["rgb"])
        corners = [world_to_pixel(camera["matrix"], p)
                   for p in ((x0,y0),(x1,y0),(x0,y1),(x1,y1))]
        left = max(0, math.floor(min(p[0] for p in corners)))
        right = min(width, math.ceil(max(p[0] for p in corners)))
        top = max(0, math.floor(min(p[1] for p in corners)))
        bottom = min(height, math.ceil(max(p[1] for p in corners)))
        clean.append((kind, geometry, color, (left, top, right, bottom)))
    pixels = bytearray(bytes(back) * (width * height))
    a, b, tx = first
    c, d, ty = second
    ia, ib, ic, id_ = d/determinant, -b/determinant, -c/determinant, a/determinant
    for kind, geometry, color, (left, top, right, bottom) in clean:
        color_bytes = bytes(color)
        for row in range(top, bottom):
            v = row + 0.5 - ty
            for col in range(left, right):
                u = col + 0.5 - tx
                x, y = ia*u+ib*v, ic*u+id_*v
                if kind == "rect":
                    x0,y0,x1,y1 = geometry
                    inside = x0 <= x < x1 and y0 <= y < y1
                else:
                    cx,cy,radius = geometry
                    inside = (x-cx)**2 + (y-cy)**2 <= radius**2
                if inside:
                    index = (row*width + col)*3
                    pixels[index:index+3] = color_bytes
    if noise:
        rng = random.Random(noise_seed)
        for i, value in enumerate(pixels):
            pixels[i] = max(0, min(255, value + rng.randrange(-noise, noise+1)))
    return image_envelope(encode_png(width, height, bytes(pixels)))


def detect_components(image: dict, rgb, tolerance: int = 8, min_pixels: int = 1) -> list[dict]:
    """Find 4-connected regions within a per-channel RGB interval.

    This is a task-aware color-segmentation reference, not a general vision
    model.  ``center`` is the mean of pixel centers; ``bbox`` uses inclusive
    integer pixel indices.  Returned geometry describes visible pixels only.
    """
    width, height, pixels = decode_envelope(image)
    color = _color(rgb)
    _integer(tolerance, 0, 64, "color tolerance")
    _integer(min_pixels, 1, MAX_PIXELS, "minimum component size")
    selected = bytearray(width * height)
    r,g,b = color
    for index in range(width * height):
        base = index * 3
        if (abs(pixels[base]-r) <= tolerance and abs(pixels[base+1]-g) <= tolerance and
                abs(pixels[base+2]-b) <= tolerance):
            selected[index] = 1
    components = []
    for start in range(width * height):
        if not selected[start]:
            continue
        selected[start] = 0
        queue = deque([start])
        area = 0
        sumx = sumy = 0
        xmin = xmax = start % width
        ymin = ymax = start // width
        while queue:
            index = queue.popleft()
            x, y = index % width, index // width
            area += 1
            sumx += x
            sumy += y
            xmin, xmax = min(xmin,x), max(xmax,x)
            ymin, ymax = min(ymin,y), max(ymax,y)
            neighbors = []
            if x: neighbors.append(index-1)
            if x+1 < width: neighbors.append(index+1)
            if y: neighbors.append(index-width)
            if y+1 < height: neighbors.append(index+width)
            for neighbor in neighbors:
                if selected[neighbor]:
                    selected[neighbor] = 0
                    queue.append(neighbor)
        if area >= min_pixels:
            components.append({"center":[sumx/area+0.5,sumy/area+0.5],
                               "bbox":[xmin,ymin,xmax,ymax],"area":area})
    return sorted(components, key=lambda value: (-value["area"], value["bbox"]))


def recover_calibration(image: dict, landmarks: list[dict], tolerance: int = 8) -> list[list[float]]:
    """Estimate a 2x3 affine camera from three named visible color landmarks.

    Each landmark is exactly ``{'world':[x,y], 'rgb':[r,g,b]}``.  Its single
    detected component supplies a pixel centroid.  Ambiguous, absent or
    collinear landmarks fail closed.  This function provides a point estimate,
    not a statistical calibration certificate.
    """
    if type(landmarks) is not list or len(landmarks) != 3:
        raise ValueError("three landmarks are required")
    world, image_points = [], []
    colors = []
    for landmark in landmarks:
        if type(landmark) is not dict or set(landmark) != {"world", "rgb"}:
            raise ValueError("invalid landmark")
        world.append(_point(landmark["world"]))
        color = _color(landmark["rgb"])
        if color in colors:
            raise ValueError("landmark colors must be distinct")
        colors.append(color)
        components = detect_components(image, color, tolerance=tolerance, min_pixels=4)
        if len(components) != 1:
            raise ValueError("landmark is absent or ambiguous")
        image_points.append(components[0]["center"])
    x0,y0 = world[0]
    dx1,dy1 = world[1][0]-x0,world[1][1]-y0
    dx2,dy2 = world[2][0]-x0,world[2][1]-y0
    determinant = dx1*dy2 - dy1*dx2
    if abs(determinant) < 1e-9:
        raise ValueError("landmark world positions are collinear")
    matrix = []
    for axis in (0,1):
        z0 = image_points[0][axis]
        dz1,dz2 = image_points[1][axis]-z0,image_points[2][axis]-z0
        first = (dz1*dy2-dz2*dy1)/determinant
        second = (dx1*dz2-dx2*dz1)/determinant
        matrix.append([first,second,z0-first*x0-second*y0])
    _matrix(matrix)
    return matrix
