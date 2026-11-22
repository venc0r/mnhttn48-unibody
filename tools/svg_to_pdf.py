#!/usr/bin/env python3
"""
1:1 PDF from the SVG that tools/layout.py writes, without external tools.

    tools/svg_to_pdf.py docs/images/layout.svg docs/images/layout.pdf

Handles only the subset layout.py emits: an mm sized <svg> with a viewBox in mm, <rect>, <line>,
<polygon>, <text> (monospace, rendered as Courier) and <g transform="translate(..) rotate(..)">,
stroke colours, widths and dash arrays. The page gets the SVG's size and the PDF asks viewers not
to scale it when printing.
"""

import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PT_PER_MM = 72 / 25.4
COURIER_ADVANCE = 0.6           # Courier glyph width per font size unit
SVG_NS = "{http://www.w3.org/2000/svg}"


def rgb(colour):
    """'#06c' or '#0066cc' -> 'r g b' in 0..1."""
    hex_digits = colour.lstrip("#")
    if len(hex_digits) == 3:
        hex_digits = "".join(digit * 2 for digit in hex_digits)
    return " ".join(f"{int(hex_digits[i:i + 2], 16) / 255:.3f}" for i in (0, 2, 4))


def number(element, name, default=0.0):
    return float(element.get(name, default))


def stroke_state(element):
    dash = element.get("stroke-dasharray")
    dash_operator = f"[{dash}] 0 d" if dash else "[] 0 d"
    return f"{rgb(element.get('stroke', '#000'))} RG {number(element, 'stroke-width', 0.3):.3f} w {dash_operator}\n"


def pdf_string(text):
    return "(" + text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def transform_matrix(transform):
    """'translate(x y) rotate(a)' -> PDF cm operands. SVG and PDF share the a b c d e f order."""
    matrix = "1 0 0 1 0 0 cm\n"
    for operation, arguments in re.findall(r"(\w+)\(([^)]*)\)", transform or ""):
        values = [float(value) for value in re.split(r"[ ,]+", arguments.strip())]
        if operation == "translate":
            matrix += f"1 0 0 1 {values[0]:.3f} {values[1] if len(values) > 1 else 0:.3f} cm\n"
        elif operation == "rotate":
            c, s = math.cos(math.radians(values[0])), math.sin(math.radians(values[0]))
            matrix += f"{c:.6f} {s:.6f} {-s:.6f} {c:.6f} 0 0 cm\n"
    return matrix


def draw(element):
    """PDF content operators for one SVG element, coordinates in SVG user units (mm, y down)."""
    tag = element.tag.replace(SVG_NS, "")
    if tag == "g":
        return "q\n" + transform_matrix(element.get("transform")) + "".join(draw(child) for child in element) + "Q\n"
    if tag == "rect":
        x, y = number(element, "x"), number(element, "y")
        return stroke_state(element) + f"{x:.3f} {y:.3f} {number(element, 'width'):.3f} {number(element, 'height'):.3f} re S\n"
    if tag == "line":
        return stroke_state(element) + (f"{number(element, 'x1'):.3f} {number(element, 'y1'):.3f} m "
                                        f"{number(element, 'x2'):.3f} {number(element, 'y2'):.3f} l S\n")
    if tag == "polygon":
        values = [float(value) for value in re.split(r"[ ,]+", element.get("points").strip())]
        points = list(zip(values[0::2], values[1::2]))
        path = f"{points[0][0]:.3f} {points[0][1]:.3f} m " + " ".join(f"{x:.3f} {y:.3f} l" for x, y in points[1:])
        return stroke_state(element) + path + " h S\n"
    if tag == "text":
        text = "".join(element.itertext())
        size = number(element, "font-size", 3.0)
        width = COURIER_ADVANCE * size * len(text)
        shift = {"middle": width / 2, "end": width}.get(element.get("text-anchor"), 0.0)
        x, y = number(element, "x") - shift, number(element, "y")
        # the page space is flipped (y down), the text matrix flips the glyphs back upright
        return (f"{rgb(element.get('fill', '#000'))} rg BT /F1 {size:.3f} Tf 1 0 0 -1 {x:.3f} {y:.3f} Tm "
                f"{pdf_string(text)} Tj ET\n")
    return ""


def svg_to_pdf(svg_path, pdf_path):
    root = ET.parse(svg_path).getroot()
    width_mm, height_mm = (float(root.get(name).removesuffix("mm")) for name in ("width", "height"))
    view_x, view_y, view_w, view_h = (float(value) for value in root.get("viewBox").split())
    page_w, page_h = width_mm * PT_PER_MM, height_mm * PT_PER_MM
    scale_x, scale_y = page_w / view_w, page_h / view_h
    content = (f"{scale_x:.6f} 0 0 {-scale_y:.6f} {-view_x * scale_x:.4f} {page_h + view_y * scale_y:.4f} cm\n"
               "0 J 0 j\n" + "".join(draw(child) for child in root)).encode("latin-1")   # butt caps: lines end where the SVG says
    objects = [
        "<< /Type /Catalog /Pages 2 0 R /ViewerPreferences << /PrintScaling /None >> >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w:.4f} {page_h:.4f}] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        None,
        "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        if body is None:
            output += f"{index} 0 obj\n<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream\nendobj\n"
        else:
            output += f"{index} 0 obj\n{body}\nendobj\n".encode()
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    output += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    output += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    Path(pdf_path).write_bytes(output)


if __name__ == "__main__":
    svg_to_pdf(sys.argv[1], sys.argv[2])
