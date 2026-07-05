from PIL import Image
import os , shutil , json
from PIL import Image
import fitz
from io import BytesIO
from utils.pdf_colors import color_to_hex 
from services.ocr_service import run_ocr_for_pdf , sample_bg_color_of_pdf
from utils.pdf_texts import pdf_map_font_to_css
from utils.pdf_utils import (
   PDF_RENDER_SCALE 
)
from config import log , TEMP_DIR
from utils.pdf_edit_utils import load_meta , save_meta , numeric_sort_key



def render_page_normal_of_pdf(pdf_page, scale, img_path):
    """Render page with all content intact. Returns (w_px, h_px)."""
    mat = fitz.Matrix(scale, scale)
    pix = pdf_page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)
    pix.save(img_path)
    return pix.width, pix.height


def extract_text_metadata_from_pdf(pdf_page, scale, rendered_img_path):
    """
    Extract invisible edit hotspots from PDF page.
    visible=False: these divs are transparent until the user edits them.
    The canvas shows the real PDF rendering underneath.
    """
    layers = []
    try:
        page_dict = pdf_page.get_text(
            "dict",
            flags=(fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES)
        )
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = span.get("text", "").rstrip("\n")
                    if not txt.strip():
                        continue

                    b  = span["bbox"]
                    x0, y0 = b[0]*scale, b[1]*scale
                    x1, y1 = b[2]*scale, b[3]*scale
                    w  = max(x1-x0, 8.0)
                    h  = max(y1-y0, 4.0)

                    fs = max(4.0, min(span.get("size", 12.0)*scale, 800.0))

                    raw_font  = span.get("font", "Arial")
                    css_font  = pdf_map_font_to_css(raw_font)
                    color     = color_to_hex(span.get("color", 0))
                    flags     = span.get("flags", 0)
                    is_bold   = bool(flags & (1<<4)) or any(x in raw_font for x in ["Bold","Heavy","Black","Demi"])
                    is_italic = bool(flags & (1<<1)) or any(x in raw_font for x in ["Italic","Oblique"])
                    bg_color  = sample_bg_color_of_pdf(rendered_img_path, x0, y0, w, h)

                    layers.append({
                        "text":      txt,
                        "x":         round(x0, 2),
                        "y":         round(y0, 2),
                        "w":         round(w,  2),
                        "h":         round(h,  2),
                        "fs":        round(fs, 2),
                        "font":      css_font,
                        "color":     color,
                        "bold":      is_bold,
                        "italic":    is_italic,
                        "underline": False,
                        "align":     "left",
                        "opacity":   1.0,
                        "bg_color":  bg_color,
                        "source":    "pdf",
                        "visible":   False,   # ← INVISIBLE: canvas shows real text
                        "edited":    False,
                    })
    except Exception as e:
        log.error(f"extract_text_metadata_from_pdf: {e}", exc_info=True)
    return layers


def pdf_page_has_native_text(pdf_page):
    return len(pdf_page.get_text("text").strip()) > 5



def save_pdf_source_file(fid, ext, raw):
    
    src_path = os.path.join(
        TEMP_DIR,
        f"{fid}.{ext}"
    )

    with open(src_path, "wb") as f:
        f.write(raw)

    return src_path




def process_pdf_pages(fid, src_path, log):
    
    pages = []

    doc = fitz.open(src_path)

    scale = PDF_RENDER_SCALE

    for i, pdf_page in enumerate(doc):

        img_path = os.path.join(
            TEMP_DIR,
            f"{fid}_page_{i}.png"
        )

        has_native = pdf_page_has_native_text(
            pdf_page
        )

        w_px, h_px = render_page_normal_of_pdf(
            pdf_page,
            scale,
            img_path
        )

        layers = (
            extract_text_metadata_from_pdf(
                pdf_page,
                scale,
                img_path
            )
            if has_native
            else run_ocr_for_pdf(img_path)
        )

        pages.append({
            "img":
                f"/temp/{fid}_page_{i}.png",

            "layers": layers,

            "width": w_px,

            "height": h_px,

            "scale": scale,

            "has_native": has_native,
        })

        log.info(
            f"Page {i}: {w_px}×{h_px}, {len(layers)} spans"
        )

    doc.close()

    return pages



def process_pdf_image_page(fid, raw):
    
    pages = []

    pil = Image.open(BytesIO(raw))

    if pil.mode == "RGBA":

        bg = Image.new(
            "RGB",
            pil.size,
            (255, 255, 255)
        )

        bg.paste(
            pil,
            mask=pil.split()[3]
        )

        pil = bg

    elif pil.mode != "RGB":

        pil = pil.convert("RGB")

    img_path = os.path.join(
        TEMP_DIR,
        f"{fid}_page_0.png"
    )

    pil.save(
        img_path,
        format="PNG",
        compress_level=1
    )

    layers = run_ocr_for_pdf(img_path)

    pages.append({
        "img":
            f"/temp/{fid}_page_0.png",

        "layers": layers,

        "width": pil.width,

        "height": pil.height,

        "scale": 1.0,

        "has_native": False,
    })

    return pages



def get_pdf_page_paths(
    file_id,
    page_index
):

    img_path = os.path.join(
        TEMP_DIR,
        f"{file_id}_page_{page_index}.png"
    )

    backup_path = os.path.join(
        TEMP_DIR,
        f"{file_id}_page_{page_index}_backup.png"
    )

    return img_path, backup_path


def create_pdf_backup_if_needed(
    img_path,
    backup_path
):

    if (
        os.path.exists(img_path)
        and not os.path.exists(backup_path)
    ):

        shutil.copy2(
            img_path,
            backup_path
        )


def save_pdf_page_image(
    img_file,
    img_path
):

    img = Image.open(img_file)

    if img.mode != "RGB":
        img = img.convert("RGB")

    img.save(
        img_path,
        format="PNG",
        compress_level=1
    )


def update_pdf_page_layers(
    file_id,
    page_index,
    layers_json
):

    if not layers_json:
        return

    try:

        meta = load_meta(file_id)

        if (
            "pages" in meta
            and page_index < len(meta["pages"])
        ):

            meta["pages"][page_index]["layers"] = \
                json.loads(layers_json)

            save_meta(file_id, meta)

    except Exception as e:

        log.warning(f"layer meta: {e}")


def get_pdf_only_page_filenames(file_id):

    return sorted(
        [
            f for f in os.listdir(TEMP_DIR)
            if (
                f.startswith(file_id + "_page_")
                and f.endswith(".png")
                and "_backup" not in f
            )
        ],
        key=numeric_sort_key
    )


def get_pdf_rebuild_scale(
    file_id
):

    meta = load_meta(file_id)

    scale = PDF_RENDER_SCALE

    if (
        "pages" in meta
        and meta["pages"]
    ):

        scale = meta["pages"][0].get(
            "scale",
            scale
        )

    return scale


def insert_png_page_into_pdf(
    pdf_doc,
    img_path,
    scale
):

    pil = Image.open(img_path).convert("RGB")

    w_px, h_px = pil.size

    pt_w = w_px / scale
    pt_h = h_px / scale

    page = pdf_doc.new_page(
        width=pt_w,
        height=pt_h
    )

    buf = BytesIO()

    pil.save(
        buf,
        format="PNG"
    )

    buf.seek(0)

    page.insert_image(
        fitz.Rect(0, 0, pt_w, pt_h),
        stream=buf.read()
    )


def build_pdf_only_document(
    fnames,
    scale
):

    pdf_doc = fitz.open()

    for fname in fnames:

        img_path = os.path.join(
            TEMP_DIR,
            fname
        )

        insert_png_page_into_pdf(
            pdf_doc,
            img_path,
            scale
        )

    pdf_bytes = pdf_doc.tobytes(
        deflate=True,
        garbage=4
    )

    pdf_doc.close()

    return pdf_bytes


def get_restore_paths(
    file_id,
    page_index
):

    backup_path = os.path.join(
        TEMP_DIR,
        f"{file_id}_page_{page_index}_backup.png"
    )

    page_path = os.path.join(
        TEMP_DIR,
        f"{file_id}_page_{page_index}.png"
    )

    return backup_path, page_path


def restore_backup_page(
    backup_path,
    page_path
):

    if not os.path.exists(backup_path):
        return False

    shutil.copy2(
        backup_path,
        page_path
    )

    return True


def remove_file_safely(
    file_path,
    fname
):

    try:

        os.remove(file_path)

        return True

    except Exception as e:

        log.warning(f"cleanup {fname}: {e}")

        return False


def cleanup_temp_files(file_id):

    removed = 0

    for fname in list(os.listdir(TEMP_DIR)):

        if fname.startswith(file_id):

            file_path = os.path.join(
                TEMP_DIR,
                fname
            )

            deleted = remove_file_safely(
                file_path,
                fname
            )

            if deleted:
                removed += 1

    return removed


