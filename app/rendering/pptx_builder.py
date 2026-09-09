"""Native PowerPoint renderer with responsive, editorial slide layouts."""
from __future__ import annotations
from pathlib import Path
import re
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_CONNECTOR
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt
from app.schemas.presentation import PresentationSpec, SlideElement, SlideSpec
from app.rendering.layout_geometry import IMAGE_CONTENT

W, H = 13.333, 7.5
MARGIN, CONTENT_Y = .76, 2.12

def rgb(value: str) -> RGBColor: return RGBColor.from_string(value.removeprefix("#"))
def shade(hex_value: str, amount: int = 12) -> str:
    raw=hex_value.removeprefix("#"); channels=[int(raw[i:i+2],16) for i in (0,2,4)]
    return "#"+"".join(f"{max(0,min(255,c+amount)):02X}" for c in channels)

def add_shape(slide, kind, x, y, w, h, fill, line=None):
    shape=slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid(); shape.fill.fore_color.rgb=rgb(fill)
    shape.line.color.rgb=rgb(line or fill)
    return shape

def add_surface(slide, x, y, w, h, d, *, emphasis=False):
    """Shared elevated-surface primitive for every panel-like PowerPoint shape."""
    shadow=add_shape(slide,MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,x+.07,y+.09,w,h,"#000000","#000000")
    shadow.fill.transparency=58
    fill=shade(d.surface_color,8 if emphasis else 0)
    return add_shape(slide,MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,x,y,w,h,fill,shade(d.primary_color,-34))

def add_text(slide, text, x, y, w, h, size, color, bold=False, *, align=PP_ALIGN.LEFT, font="Arial", valign=MSO_ANCHOR.TOP):
    box=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); frame=box.text_frame
    frame.clear(); frame.word_wrap=True; frame.margin_left=frame.margin_right=0; frame.margin_top=frame.margin_bottom=0; frame.vertical_anchor=valign
    p=frame.paragraphs[0]; p.text=(text or "").strip(); p.alignment=align
    p.font.size=Pt(size); p.font.bold=bold; p.font.name=font; p.font.color.rgb=rgb(color)
    return box

def text_size(text: str, base: int, width: float) -> int:
    """Conservative deterministic sizing, avoiding reliance on host font metrics."""
    density=len(text or "") / max(width, .5)
    # Copy must be shortened upstream; never solve poor composition by tiny type.
    return max(16, base-4) if density>95 else max(16,base-2) if density>65 else base

def clean_copy(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\\n", " ").replace("\n", " ")).strip()

def element_text(element: SlideElement) -> str:
    return clean_copy(element.body or element.subtext or element.value or "")

def bullet_points(element: SlideElement, limit: int = 3) -> list[str]:
    raw=(element.body or element.subtext or element.value or "").replace("\\n", "\n")
    chunks=re.split(r"\n+|\s*[•▪]\s*", raw)
    points=[clean_copy(point) for point in chunks if clean_copy(point)]
    if len(points)<2:
        points=[clean_copy(point) for point in re.split(r"(?<=[.!?])\s+", raw) if clean_copy(point)]
    return [point[:115].rsplit(" ",1)[0] if len(point)>115 else point for point in points[:limit]]

def add_bullets(slide, points: list[str], x, y, w, h, d):
    box=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); frame=box.text_frame
    frame.clear(); frame.word_wrap=True; frame.margin_left=frame.margin_right=0; frame.margin_top=frame.margin_bottom=0
    for index, point in enumerate(points):
        p=frame.paragraphs[0] if index==0 else frame.add_paragraph(); p.text=f"• {point}"; p.font.size=Pt(16); p.font.name=d.font_body; p.font.color.rgb=rgb(d.text_secondary); p.space_after=Pt(12)
    return box

def header(slide, spec: SlideSpec, d):
    add_shape(slide, MSO_AUTO_SHAPE_TYPE.RECTANGLE, 0, 0, W, .10, d.primary_color)
    # Keep the title clear of the icon and slide number.  A slightly more
    # conservative fixed cap produces the same result across PowerPoint,
    # Keynote, and LibreOffice, whose font metrics differ from a browser.
    add_text(slide, spec.title, MARGIN, .43, 9.9, .76, text_size(spec.title, 32, 9.9), d.header_color, True, font=d.font_heading)
    if spec.subtitle: add_text(slide, spec.subtitle, MARGIN, 1.38, 10.6, .36, 16, d.text_secondary, font=d.font_body)
    topic_icon(slide,str(spec.visual_spec.get("icon_concept","")),11.28,.52,d)
    add_text(slide, f"{spec.slide_number:02d}", 11.86, .61, .65, .28, 10, d.muted_text, True, align=PP_ALIGN.RIGHT)

def accent_orb(slide, x, y, size, d):
    circle=add_shape(slide, MSO_AUTO_SHAPE_TYPE.OVAL, x, y, size, size, shade(d.primary_color, -70), d.primary_color)
    circle.fill.transparency=18

def depth_orb(slide, x, y, size, d):
    """Native layered transparency approximates the browser preview's radial depth."""
    outer=add_shape(slide,MSO_AUTO_SHAPE_TYPE.OVAL,x,y,size,size,shade(d.primary_color,-95),shade(d.primary_color,-95)); outer.fill.transparency=34
    middle=add_shape(slide,MSO_AUTO_SHAPE_TYPE.OVAL,x+size*.15,y+size*.15,size*.68,size*.68,shade(d.primary_color,-48),shade(d.primary_color,-48)); middle.fill.transparency=35
    inner=add_shape(slide,MSO_AUTO_SHAPE_TYPE.OVAL,x+size*.32,y+size*.29,size*.36,size*.36,d.primary_color,d.primary_color); inner.fill.transparency=58

def comparison_cover_visual(slide, title: str, d):
    """A topic-aware focal visual for comparison covers, kept fully editable."""
    parts=re.split(r"\s+(?:vs\.?|versus)\s+", title, maxsplit=1, flags=re.I)
    if len(parts)!=2 or not all(part.strip() for part in parts):
        depth_orb(slide,8.95,1.05,3.05,d)
        return
    left, right=(part.strip() for part in parts)
    # Two equal fields communicate a decision without implying that one choice
    # wins before the deck has presented the criteria.
    for x, label, fill, opacity in ((8.52,left,shade(d.primary_color,-58),24),(10.78,right,d.primary_color,14)):
        circle=add_shape(slide,MSO_AUTO_SHAPE_TYPE.OVAL,x,1.72,1.88,1.88,fill,d.primary_color)
        circle.fill.transparency=opacity
        add_text(slide,label,x+.16,2.48,1.56,.28,text_size(label,16,1.56),"#FFFFFF",True,align=PP_ALIGN.CENTER,font=d.font_heading)
    add_text(slide,"vs.",10.28,2.43,.62,.22,13,d.primary_color,True,align=PP_ALIGN.CENTER,font=d.font_heading)

def topic_icon(slide, concept: str, x: float, y: float, d):
    """Editable native icon selected from the visual director's topic-specific concept."""
    concept=(concept or "").lower(); stroke=d.primary_color
    if any(word in concept for word in ("scale","growth","metric","performance")):
        for i,height in enumerate((.16,.30,.48)): add_shape(slide,MSO_AUTO_SHAPE_TYPE.RECTANGLE,x+i*.16,y+.5-height,.10,height,stroke,stroke)
    elif any(word in concept for word in ("security","risk","shield","govern")):
        add_shape(slide,MSO_AUTO_SHAPE_TYPE.PENTAGON,x+.05,y,.42,.48,shade(d.surface_color,8),stroke)
    elif any(word in concept for word in ("architecture","deploy","service","cluster","system")):
        for dx,dy in ((.02,.02),(.34,.02),(.18,.32)): add_shape(slide,MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,x+dx,y+dy,.14,.14,stroke,stroke)
    else: accent_orb(slide,x,y,.48,d)

def card(slide, element, x, y, w, h, d, index: int, emphasis=False):
    add_surface(slide,x,y,w,h,d,emphasis=emphasis)
    compact=h<2
    add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, x+.22, y+.22, .38, .38, d.primary_color, d.primary_color)
    add_text(slide, str(index+1), x+.22, y+.29, .38, .16, 8, d.background_color, True, align=PP_ALIGN.CENTER)
    heading=element.heading or element.label or "Key insight"
    body=element_text(element)
    if compact:
        add_text(slide, heading, x+.78, y+.22, w-1.02, .3, 16, d.text_primary, True, font=d.font_heading)
        add_text(slide, body, x+.78, y+.65, w-1.02, .3, 16, d.text_secondary, font=d.font_body)
    else:
        add_text(slide, heading, x+.24, y+.74, w-.48, .52, text_size(heading, 24, w-.48), d.text_primary, True, font=d.font_heading)
        add_text(slide, body, x+.24, y+1.38, w-.48, h-1.58, text_size(body, 16, w-.48), d.text_secondary, font=d.font_body)

def grid_cards(slide, spec, d):
    elements=spec.elements[:6]; count=len(elements)
    columns=2 if count in (2,4,6) else min(3,max(1,count)); rows=(count+columns-1)//columns
    gap=.24; total_w=W-2*MARGIN; card_w=(total_w-gap*(columns-1))/columns; card_h=min(3.95,(4.62-gap*(rows-1))/rows)
    for i, item in enumerate(elements):
        col,row=i%columns,i//columns
        card(slide,item,MARGIN+col*(card_w+gap),CONTENT_Y+row*(card_h+gap),card_w,card_h,d,i,emphasis=i==0)

def workflow(slide, spec, d):
    items=spec.elements[:4]; n=max(1,len(items)); gap=.36; width=(W-2*MARGIN-gap*(n-1))/n
    for i, item in enumerate(items):
        x=MARGIN+i*(width+gap); accent_orb(slide,x+width/2-.28,2.28,.56,d)
        add_text(slide,str(i+1),x+width/2-.28,2.46,.56,.14,9,d.background_color,True,align=PP_ALIGN.CENTER)
        if i<n-1:
            connector=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x+width+.06), Inches(2.56), Inches(x+width+gap-.06), Inches(2.56)); connector.line.color.rgb=rgb(d.primary_color); connector.line.width=Pt(1.5)
        add_text(slide,item.heading or f"Step {i+1}",x,3.05,width,.48,text_size(item.heading or "",16,width),d.text_primary,True,align=PP_ALIGN.CENTER,font=d.font_heading)
        add_text(slide,element_text(item),x+.08,3.72,width-.16,1.1,text_size(element_text(item),12,width-.16),d.text_secondary,align=PP_ALIGN.CENTER)

def two_columns(slide, spec, d):
    items=(spec.elements+[SlideElement(heading="",body=""),SlideElement(heading="",body="")])[:2]
    for i,item in enumerate(items):
        x=MARGIN+i*6.05
        add_surface(slide,x,CONTENT_Y,5.82,3.92,d,emphasis=i==0)
        add_shape(slide,MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,x+.26,CONTENT_Y+.28,.43,.43,d.primary_color,d.primary_color)
        add_text(slide,str(i+1),x+.26,CONTENT_Y+.37,.43,.14,9,d.background_color,True,align=PP_ALIGN.CENTER)
        add_text(slide,item.heading or "Decision criteria",x+.28,CONTENT_Y+.98,5.2,.55,text_size(item.heading or "",24,5.2),d.text_primary,True,font=d.font_heading)
        add_bullets(slide,bullet_points(item),x+.3,CONTENT_Y+1.72,5.1,1.75,d)

def architecture(slide, spec, d):
    items=spec.elements[:4]
    for i,item in enumerate(items):
        y=CONTENT_Y+i*1.0; inset=.28*i
        add_surface(slide,MARGIN+inset,y,11.8-2*inset,.80,d,emphasis=i==0)
        add_text(slide,item.heading or f"Layer {i+1}",MARGIN+.28+inset,y+.15,3.0,.32,18,d.primary_color,True,font=d.font_heading)
        add_text(slide,element_text(item),MARGIN+3.42+inset,y+.17,7.8-2*inset,.34,16,d.text_secondary)

def title_slide(slide, spec, d):
    dynamic_path=spec.visual_spec.get("image_path")
    cover=Path(dynamic_path) if dynamic_path else None
    text_width=7.65
    if cover and cover.exists():
        # Supplying one dimension preserves the generated image's native aspect ratio.
        slide.shapes.add_picture(str(cover), Inches(8.72), Inches(1.02), height=Inches(5.78))
        add_shape(slide,MSO_AUTO_SHAPE_TYPE.RECTANGLE,8.62,1.02,.10,5.78,d.primary_color,d.primary_color)
    else:
        comparison_cover_visual(slide,spec.title,d)
    add_text(slide,"DECKFORGE / BRIEF",MARGIN,1.12,3.0,.24,10,d.primary_color,True)
    add_text(slide,spec.title,MARGIN,1.62,text_width,2.52,text_size(spec.title,50,text_width),d.header_color,True,font=d.font_heading)
    subtitle=spec.subtitle or spec.purpose
    add_text(slide,subtitle,MARGIN,4.52,7.2,.66,20,d.text_secondary)

def add_picture_cover(slide, image_path: Path, x: float, y: float, w: float, h: float):
    """Place a raster visual inside an exact canvas frame without spillover."""
    from PIL import Image
    with Image.open(image_path) as image:
        source_ratio=image.width / image.height
    frame_ratio=w / h
    picture=slide.shapes.add_picture(str(image_path), Inches(x), Inches(y), Inches(w), Inches(h))
    if source_ratio > frame_ratio:
        crop=(1 - frame_ratio / source_ratio) / 2
        picture.crop_left=crop; picture.crop_right=crop
    elif source_ratio < frame_ratio:
        crop=(1 - source_ratio / frame_ratio) / 2
        picture.crop_top=crop; picture.crop_bottom=crop
    return picture

def content_with_visual(slide, spec, d):
    image_path=Path(str(spec.visual_spec["image_path"]))
    lead_x,lead_y,lead_w,lead_h=IMAGE_CONTENT["lead"]
    cards_x,cards_y,cards_w,_=IMAGE_CONTENT["cards"]
    image_x,image_y,image_w,image_h=IMAGE_CONTENT["image"]
    add_surface(slide,image_x,image_y,image_w,image_h,d,emphasis=True)
    add_picture_cover(slide,image_path,image_x+.10,image_y+.10,image_w-.20,image_h-.20)
    add_text(slide,spec.purpose,lead_x,lead_y,lead_w,lead_h,24,d.text_primary,True,font=d.font_heading)
    for index,item in enumerate(spec.elements[:3]):
        y=cards_y+index*(IMAGE_CONTENT["card_height"]+IMAGE_CONTENT["card_gap"])
        add_surface(slide,cards_x,y,cards_w,IMAGE_CONTENT["card_height"],d,emphasis=index==0)
        add_text(slide,f"{index+1:02d}",cards_x+.22,y+.18,.35,.16,10,d.primary_color,True)
        add_text(slide,item.heading or "Key point",cards_x+.22,y+.39,cards_w-.44,.24,17,d.primary_color,True,font=d.font_heading)
        add_text(slide,element_text(item),cards_x+.22,y+.68,cards_w-.44,.20,13,d.text_secondary)

def summary(slide, spec, d):
    add_surface(slide,MARGIN,CONTENT_Y,3.15,4.2,d,emphasis=True)
    add_text(slide,"THE DECISION",MARGIN+.28,CONTENT_Y+.4,2.5,.25,12,d.primary_color,True)
    add_text(slide,spec.purpose,MARGIN+.28,CONTENT_Y+1.05,2.55,2.48,22,d.text_primary,True,font=d.font_heading)
    right=spec.elements[:3]
    for i,item in enumerate(right):
        y=CONTENT_Y+i*1.35
        add_shape(slide,MSO_AUTO_SHAPE_TYPE.OVAL,4.28,y+.11,.34,.34,d.primary_color,d.primary_color)
        add_text(slide,str(i+1),4.28,y+.2,.34,.12,8,d.background_color,True,align=PP_ALIGN.CENTER)
        add_text(slide,item.heading or "Key takeaway",4.86,y,7.4,.38,20,d.text_primary,True,font=d.font_heading)
        add_text(slide,element_text(item),4.86,y+.48,7.2,.45,16,d.text_secondary)

def comparison_rows(slide, spec, d):
    add_text(slide,"DECISION LENSES",MARGIN,1.70,3.0,.20,11,d.primary_color,True)
    for index,item in enumerate(spec.elements[:3]):
        y=CONTENT_Y+index*1.22
        add_surface(slide,MARGIN,y,11.82,.94,d,emphasis=index==0)
        add_text(slide,f"{index+1:02d}",MARGIN+.26,y+.32,.36,.16,10,d.primary_color,True)
        add_text(slide,item.heading or "Decision lens",MARGIN+.92,y+.21,3.3,.28,20,d.text_primary,True,font=d.font_heading)
        add_text(slide,element_text(item),MARGIN+4.25,y+.23,6.9,.32,16,d.text_secondary)

def evidence_strip(slide, spec, d):
    items=spec.elements[:3]; count=max(1,len(items)); gap=.38; width=(W-2*MARGIN-gap*(count-1))/count
    for index,item in enumerate(items):
        x=MARGIN+index*(width+gap)
        add_shape(slide,MSO_AUTO_SHAPE_TYPE.RECTANGLE,x,CONTENT_Y,.08,3.62,d.primary_color,d.primary_color)
        add_text(slide,f"0{index+1}",x+.28,CONTENT_Y+.12,width-.28,.24,12,d.primary_color,True)
        add_text(slide,item.heading or "Evidence",x+.28,CONTENT_Y+.72,width-.38,.65,26,d.text_primary,True,font=d.font_heading)
        add_text(slide,element_text(item),x+.28,CONTENT_Y+1.72,width-.38,1.08,17,d.text_secondary)

def asymmetric_insight(slide, spec, d):
    add_text(slide,spec.purpose,MARGIN,CONTENT_Y+.18,5.0,1.48,30,d.text_primary,True,font=d.font_heading)
    for index,item in enumerate(spec.elements[:2]):
        y=CONTENT_Y+index*1.74
        add_surface(slide,6.3,y,6.25,1.35,d,emphasis=index==0)
        add_text(slide,item.heading or "Key point",6.62,y+.25,5.55,.28,21,d.primary_color,True,font=d.font_heading)
        add_text(slide,element_text(item),6.62,y+.70,5.55,.32,16,d.text_secondary)

def section_interlude(slide, spec, d):
    """Minimal breathing room between dense content sections."""
    depth_orb(slide,9.15,1.48,2.3,d)
    add_text(slide,"SECTION",MARGIN,1.55,2.0,.22,11,d.primary_color,True)
    add_text(slide,spec.title,MARGIN,2.00,7.4,1.15,text_size(spec.title,44,7.4),d.header_color,True,font=d.font_heading)
    add_text(slide,spec.subtitle or spec.purpose,MARGIN,3.35,6.7,.52,19,d.text_secondary,font=d.font_body)

def add_slide_transition(slide, transition_name: str | None):
    """Write supported native PowerPoint slide transitions into the OOXML.

    Element-level animation is intentionally not fabricated here: it has a
    substantially more complex timing model and is not supported by python-pptx.
    """
    name=(transition_name or "fade").lower()
    if name not in {"fade", "push", "wipe"}: name="fade"
    transition=OxmlElement("p:transition")
    transition.set("spd", "med")
    transition.set("advClick", "1")
    effect=OxmlElement(f"p:{name}")
    if name in {"push", "wipe"}: effect.set("dir", "l")
    transition.append(effect)
    slide._element.insert_element_before(transition, "p:timing", "p:extLst")

def build_presentation(spec: PresentationSpec, destination: str | Path) -> Path:
    prs=Presentation(); prs.slide_width=Inches(W); prs.slide_height=Inches(H); blank=prs.slide_layouts[6]; d=spec.design_system
    for spec_slide in spec.slides:
        slide=prs.slides.add_slide(blank); slide.background.fill.solid(); slide.background.fill.fore_color.rgb=rgb(d.background_color)
        if spec_slide.layout_type.value=="title_slide": title_slide(slide,spec_slide,d)
        elif spec_slide.layout_type.value=="section_slide": section_interlude(slide,spec_slide,d)
        else:
            header(slide,spec_slide,d)
            layout=spec_slide.layout_type.value
            if spec_slide.visual_spec.get("image_path"): content_with_visual(slide,spec_slide,d)
            elif layout in {"step_workflow","process_flow","timeline"}: workflow(slide,spec_slide,d)
            elif layout=="architecture_layers": architecture(slide,spec_slide,d)
            elif layout=="two_column": two_columns(slide,spec_slide,d)
            elif layout=="comparison": comparison_rows(slide,spec_slide,d)
            elif layout=="key_metrics": evidence_strip(slide,spec_slide,d)
            elif layout=="content_with_visual": asymmetric_insight(slide,spec_slide,d)
            elif layout=="summary": summary(slide,spec_slide,d)
            else: grid_cards(slide,spec_slide,d)
        add_text(slide,str(spec_slide.slide_number),12.05,6.92,.42,.18,9,d.muted_text,True,align=PP_ALIGN.RIGHT)
        add_slide_transition(slide, spec_slide.visual_spec.get("transition"))
    path=Path(destination); path.parent.mkdir(parents=True,exist_ok=True); prs.save(path); return path
