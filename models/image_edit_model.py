from utils.pdf_colors import rgb_to_hex , int_color_to_hex
from PIL import Image
import os, json, shutil , collections
import fitz
from config import log , TEMP_DIR
from services.ocr_service import run_ocr_for_image , sample_bg_color , sample_text_color
from utils.pdf_utils import PDF_RENDER_SCALE
from io import BytesIO
from utils.pdf_edit_utils import save_meta , load_meta , numeric_sort_key

    
    
    
# ── PDF helpers ────────────────────────────────────────────────────────────
def extract_native(pdf_page, scale):
    out=[]
    try:
        for block in pdf_page.get_text("dict",flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
            if block.get("type")!=0: continue
            for line in block.get("lines",[]):
                for span in line.get("spans",[]):
                    txt=span.get("text","").strip()
                    if not txt: continue
                    b=span["bbox"]; x0,y0=b[0]*scale,b[1]*scale; x1,y1=b[2]*scale,b[3]*scale
                    w=max(x1-x0,20); h=max(y1-y0,8)
                    fs=max(6.0,min(round(span.get("size",12)*scale,1),300.0))
                    fname=span.get("font","Arial").split("+")[-1]
                    color=int_color_to_hex(span.get("color",0)); flags=span.get("flags",0)
                    out.append({"text":txt,"x":round(x0,2),"y":round(y0,2),
                                "w":round(w,2),"h":round(h,2),"font_size":fs,
                                "font":fname,"color":color,
                                "bold":"Bold" in fname or bool(flags&(1<<4)),
                                "italic":"Italic" in fname or "Oblique" in fname or bool(flags&(1<<1)),
                                "underline":"Underline" in fname,
                                "align":"left","opacity":1.0,"source":"pdf",
                                "bg_color":"#ffffff","edited":False})
    except Exception as e: log.error(f"extract_native: {e}")
    return out



def get_pdf_page_bg_color(pdf_page, scale):
    try:
        mat=fitz.Matrix(0.2,0.2)
        pix=pdf_page.get_pixmap(matrix=mat,alpha=False,colorspace=fitz.csRGB)
        samples=pix.samples; W,H=pix.width,pix.height; pixels=[]
        for cx,cy in [(0,0),(W-1,0),(0,H-1),(W-1,H-1)]:
            idx=(cy*W+cx)*3
            if idx+2<len(samples): pixels.append((samples[idx],samples[idx+1],samples[idx+2]))
        if not pixels: return "#ffffff"
        return rgb_to_hex((int(sum(p[0] for p in pixels)/len(pixels)),
                           int(sum(p[1] for p in pixels)/len(pixels)),
                           int(sum(p[2] for p in pixels)/len(pixels))))
    except: return "#ffffff"

def render_pdf_no_text(pdf_page, scale, bg_color_hex="#ffffff"):
    try:
        h=bg_color_hex.lstrip("#")
        bg_r,bg_g,bg_b=(int(h[0:2],16)/255,int(h[2:4],16)/255,int(h[4:6],16)/255) if len(h)==6 else (1.,1.,1.)
        tmp=fitz.open(); tmp.insert_pdf(pdf_page.parent,from_page=pdf_page.number,to_page=pdf_page.number)
        pg=tmp[0]; found=False
        for block in pg.get_text("dict",flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks",[]):
            if block.get("type")!=0: continue
            for line in block.get("lines",[]):
                for span in line.get("spans",[]):
                    if span.get("text","").strip():
                        rect=fitz.Rect(span["bbox"])+(-1,-2,1,3)
                        pg.add_redact_annot(rect,text="",fill=(bg_r,bg_g,bg_b)); found=True
        if found: pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        mat=fitz.Matrix(scale,scale)
        pix=pg.get_pixmap(matrix=mat,alpha=False,colorspace=fitz.csRGB); tmp.close()
        return pix
    except Exception as e: log.error(f"render_pdf_no_text: {e}"); return None
    


def save_source_file(fid, ext, raw):

    src_path = os.path.join(
        TEMP_DIR,
        f"{fid}.{ext}"
    )

    with open(src_path, "wb") as f:
        f.write(raw)

    return src_path


def process_pdf_page(
    fid,
    pdf_page,
    page_index,
    scale
):

    img_path = os.path.join(
        TEMP_DIR,
        f"{fid}_page_{page_index}.png"
    )

    text_layers = extract_native(
        pdf_page,
        scale
    )

    page_bg = get_pdf_page_bg_color(
        pdf_page,
        scale
    )

    for layer in text_layers:
        layer["bg_color"] = page_bg

    if text_layers:

        pix = render_pdf_no_text(
            pdf_page,
            scale,
            bg_color_hex=page_bg
        )

        if pix is None:

            mat = fitz.Matrix(scale, scale)

            pix = pdf_page.get_pixmap(
                matrix=mat,
                alpha=False,
                colorspace=fitz.csRGB
            )

    else:

        mat = fitz.Matrix(scale, scale)

        pix = pdf_page.get_pixmap(
            matrix=mat,
            alpha=False,
            colorspace=fitz.csRGB
        )

    pix.save(img_path)

    if not text_layers:
        text_layers = run_ocr_for_image(img_path)

    return {
        "img": f"/temp/{fid}_page_{page_index}.png",
        "layers": text_layers,
        "width": pix.width,
        "height": pix.height,
        "scale": scale,
        "type": "pdf"
    }


def process_pdf_file(
    fid,
    src_path
):

    pages = []

    doc = fitz.open(src_path)

    scale = PDF_RENDER_SCALE

    for i, pdf_page in enumerate(doc):

        page_data = process_pdf_page(
            fid,
            pdf_page,
            i,
            scale
        )

        pages.append(page_data)

    doc.close()

    return pages


def process_image_file(
    fid,
    raw
):

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

    else:
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

    text_layers = run_ocr_for_image(img_path)

    iw, ih = pil.size

    pages.append({
        "img": f"/temp/{fid}_page_0.png",
        "layers": text_layers,
        "width": iw,
        "height": ih,
        "scale": 1.0,
        "type": "image"
    })

    return pages 

def get_saved_pages(file_id):

    meta = load_meta(file_id)

    if meta and "pages" in meta:
        return meta["pages"]

    return None


def get_page_filenames(file_id):

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



# ════════════════════════════════════════════════════════════════════════
# REBUILD PDF SERVICES
# ════════════════════════════════════════════════════════════════════════

def get_rebuild_page_filenames(file_id):

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


def insert_image_page_into_pdf(
    doc,
    file_path
):

    pil = Image.open(file_path).convert("RGB")

    buf = BytesIO()

    pil.save(
        buf,
        format="PDF"
    )

    buf.seek(0)

    src = fitz.open(
        "pdf",
        buf.read()
    )

    doc.insert_pdf(src)

    src.close()


def build_pdf_document(fnames):

    doc = fitz.open()

    for fn in fnames:

        file_path = os.path.join(
            TEMP_DIR,
            fn
        )

        insert_image_page_into_pdf(
            doc,
            file_path
        )

    out = BytesIO(
        doc.write()
    )

    doc.close()

    return out


# ════════════════════════════════════════════════════════════════════════
# SAVE PAGE SERVICES
# ════════════════════════════════════════════════════════════════════════

def create_backup_if_needed(
    img_path,
    backup_path
):

    if (
        os.path.exists(img_path)
        and not os.path.exists(backup_path)
    ):
        shutil.copy2(img_path, backup_path)


def save_edited_image(
    img_file,
    img_path
):

    Image.open(img_file) \
        .convert("RGB") \
        .save(
            img_path,
            "PNG",
            compress_level=1
        )


def update_page_layers(
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

    except:
        pass



def build_page_data(fname):

    ip = os.path.join(
        TEMP_DIR,
        fname
    )

    tl = run_ocr_for_image(ip)

    try:

        p2 = Image.open(ip)

        w, h = p2.size

    except:

        w, h = 0, 0

    return {
        "img": f"/temp/{fname}",
        "layers": tl,
        "width": w,
        "height": h,
        "scale": 1.0
    }


def rebuild_pages_from_images(file_id):

    pages = []

    fnames = get_page_filenames(file_id)

    if not fnames:
        return None

    for fname in fnames:

        page_data = build_page_data(fname)

        pages.append(page_data)

    save_meta(file_id, {
        "pages": pages
    })

    return pages