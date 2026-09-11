"""Native PowerPoint renderer with responsive, editorial slide layouts."""
from __future__ import annotations
from pathlib import Path
import re
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
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

def mix(first: str, second: str, amount: float) -> str:
    """Return an opaque colour between two theme colours.

    Opaque gradient stops survive PowerPoint, Keynote, and LibreOffice much
    more consistently than partially transparent background shapes.
    """
    left=first.removeprefix("#"); right=second.removeprefix("#")
    channels=[]
    for index in (0,2,4):
        start=int(left[index:index+2],16); end=int(right[index:index+2],16)
        channels.append(round(start+(end-start)*max(0,min(1,amount))))
    return "#"+"".join(f"{channel:02X}" for channel in channels)

def add_shape(slide, kind, x, y, w, h, fill, line=None):
    shape=slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid(); shape.fill.fore_color.rgb=rgb(fill)
    shape.line.color.rgb=rgb(line or fill)
    return shape

def apply_linear_gradient(shape, stops: list[tuple[int,str]], angle: int = 0):
    """Apply an OOXML gradient fill with opaque stops to an editable rectangle."""
    properties=shape._element.spPr
    for child in list(properties):
        if child.tag.endswith(("solidFill", "gradFill", "pattFill", "noFill", "blipFill")):
            properties.remove(child)
    gradient=OxmlElement("a:gradFill")
    gradient.set("rotWithShape", "1")
    stop_list=OxmlElement("a:gsLst")
    for position, colour in stops:
        stop=OxmlElement("a:gs"); stop.set("pos",str(position))
        solid=OxmlElement("a:srgbClr"); solid.set("val",colour.removeprefix("#"))
        stop.append(solid); stop_list.append(stop)
    gradient.append(stop_list)
    linear=OxmlElement("a:lin"); linear.set("ang",str(angle)); linear.set("scaled","1")
    gradient.append(linear)
    properties.insert(0,gradient)

def add_gradient_canvas(slide, stops: list[tuple[int,str]], angle: int = 0):
    """Add a non-interfering full-slide gradient before all content objects."""
    canvas=add_shape(slide,MSO_AUTO_SHAPE_TYPE.RECTANGLE,0,0,W,H,stops[0][1],stops[0][1])
    canvas.line.transparency=100
    apply_linear_gradient(canvas,stops,angle)
    return canvas

def add_surface(slide, x, y, w, h, d, *, emphasis=False):
    """Shared elevated-surface primitive for every panel-like PowerPoint shape."""
    shadow=add_shape(slide,MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,x+.07,y+.09,w,h,"#000000","#000000")
    shadow.fill.transparency=58
    fill=shade(d.surface_color,8 if emphasis else 0)
    return add_shape(slide,MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,x,y,w,h,fill,shade(d.primary_color,-34))

def apply_background_treatment(slide, treatment: str | None, d):
    """Cross-viewer-safe, theme-colour gradient backgrounds.

    Keynote flattens transparency on several native PowerPoint shapes.  The
    prior halo/spotlight implementation therefore became a giant opaque circle
    above slide content.  Use opaque gradient stops behind the content instead.
    """
    treatment=(treatment or "clean").lower()
    background=d.background_color
    if treatment=="halo":
        add_gradient_canvas(slide,[(0,background),(61000,background),(100000,mix(background,d.primary_color,.12))])
    elif treatment=="diagonal":
        add_gradient_canvas(slide,[(0,background),(64000,background),(100000,mix(background,d.primary_color,.09))],angle=2700000)
    elif treatment=="spotlight":
        add_gradient_canvas(slide,[(0,background),(52000,mix(background,d.primary_color,.045)),(100000,mix(background,d.primary_color,.13))],angle=18900000)
    elif treatment=="blueprint":
        add_gradient_canvas(slide,[(0,background),(100000,mix(background,d.primary_color,.08))],angle=2700000)

def estimated_text_height(text: str, size: int, width: float, *, bold: bool = False) -> float:
    """Conservative cross-viewer text measurement in slide inches.

    python-pptx cannot ask PowerPoint or Keynote for font metrics.  This
    estimate deliberately reserves more room than browser metrics so a saved
    deck remains readable when opened by either application.
    """
    text=clean_copy(text)
    if not text:
        return .04
    average_character_width=.56 if bold else .52
    characters_per_line=max(5,int(width*72/(max(size,1)*average_character_width)))
    lines=0
    for paragraph in text.split("\n"):
        words=paragraph.split() or [""]
        line_length=0
        for word in words:
            word_length=len(word)+(1 if line_length else 0)
            if line_length and line_length+word_length>characters_per_line:
                lines+=1; line_length=len(word)
            else:
                line_length+=word_length
        lines+=1
    return lines*size*1.34/72+.05

def fitted_text_size(text: str, preferred: int, width: float, height: float, *, bold: bool = False, minimum: int = 11) -> int:
    """Return the largest readable type size that fits the supplied lane."""
    for size in range(preferred, minimum-1, -1):
        if estimated_text_height(text,size,width,bold=bold)<=height:
            return size
    return minimum

def add_text(slide, text, x, y, w, h, size, color, bold=False, *, align=PP_ALIGN.LEFT, font="Arial", valign=MSO_ANCHOR.TOP):
    box=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); frame=box.text_frame
    frame.clear(); frame.word_wrap=True; frame.margin_left=frame.margin_right=0; frame.margin_top=frame.margin_bottom=0; frame.vertical_anchor=valign
    p=frame.paragraphs[0]; p.text=(text or "").strip(); p.alignment=align
    # This is the single fit gate used by every renderer layout.  Individual
    # layouts allocate their own lanes, but no text can silently spill outside
    # its containing shape in a downloaded PPTX.
    fitted=fitted_text_size(p.text,size,w,h,bold=bold)
    p.font.size=Pt(fitted); p.font.bold=bold; p.font.name=font; p.font.color.rgb=rgb(color)
    return box

def text_size(text: str, base: int, width: float) -> int:
    """Conservative deterministic sizing, avoiding reliance on host font metrics."""
    density=len(text or "") / max(width, .5)
    # Copy must be shortened upstream; never solve poor composition by tiny type.
    return max(16, base-4) if density>95 else max(16,base-2) if density>65 else base

def cover_title_size(text: str) -> int:
    """Keep cover text in its dedicated lane above the subtitle."""
    length=len(clean_copy(text))
    if length > 78: return 32
    if length > 58: return 38
    if length > 40: return 44
    return 50

def clean_copy(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\\n", " ").replace("\n", " ")).strip()

def element_text(element: SlideElement) -> str:
    return clean_copy(element.body or element.subtext or element.value or "")

def bullet_points(element: SlideElement, limit: int = 3) -> list[str]:
    raw=(element.body or element.subtext or element.value or "").replace("\\n", "\n")
    chunks=re.split(r"\n+|\s*[•▪]\s*", raw)
    points=[clean_copy(point) for point in chunks if clean_copy(point)]
    if len(points)<2:
        points=[clean_copy(point) for point in re.split(r"(?<=[.!?])\s*", raw) if clean_copy(point)]
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
    # Slide numbering is deliberately rendered once in the shared footer.
    # A second header number looked like a misplaced page number in Keynote.

def accent_orb(slide, x, y, size, d):
    circle=add_shape(slide, MSO_AUTO_SHAPE_TYPE.OVAL, x, y, size, size, shade(d.primary_color, -70), d.primary_color)
    circle.fill.transparency=18

def depth_orb(slide, x, y, size, d):
    """One portable focal orb, kept behind content and free of transparency."""
    orb=add_shape(slide,MSO_AUTO_SHAPE_TYPE.OVAL,x,y,size,size,d.background_color,d.background_color)
    orb.line.transparency=100
    apply_linear_gradient(
        orb,
        [(0,mix(d.background_color,d.primary_color,.28)), (100000,mix(d.background_color,d.primary_color,.025))],
        angle=18900000,
    )

def comparison_cover_visual(slide, title: str, d):
    """Use the same single focal visual as the browser cover preview.

    The title already conveys the comparison.  Labelled circles duplicated it,
    wrapped unpredictably, and created a different composition in Keynote.
    """
    depth_orb(slide,8.95,1.05,3.05,d)

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
        heading_height=.94 if len(heading)>20 else .52
        add_text(slide, heading, x+.24, y+.74, w-.48, heading_height, text_size(heading, 24, w-.48), d.text_primary, True, font=d.font_heading)
        body_y=y+.74+heading_height+.16
        add_text(slide, body, x+.24, body_y, w-.48, h-(body_y-y)-.20, text_size(body, 16, w-.48), d.text_secondary, font=d.font_body)

def grid_cards(slide, spec, d):
    elements=spec.elements[:6]
    # A provider may temporarily return no items while an explicit brief asks
    # it to draft them.  A blank, broken slide is never acceptable; render a
    # single bounded insight rather than dividing by zero or exposing private
    # instruction text.
    if not elements:
        elements=[SlideElement(heading="Key insight", body=clean_copy(spec.purpose))]
    count=len(elements)
    columns=2 if count in (2,4,6) else min(3,max(1,count)); rows=(count+columns-1)//columns
    gap=.24; total_w=W-2*MARGIN; card_w=(total_w-gap*(columns-1))/columns
    max_available=(4.62-gap*(rows-1))/rows
    required=[]
    for item in elements:
        heading=item.heading or item.label or "Key insight"; body=element_text(item)
        required.append(.74+estimated_text_height(heading,text_size(heading,24,card_w-.48),card_w-.48,bold=True)+.14+estimated_text_height(body,text_size(body,16,card_w-.48),card_w-.48))
    # Cards grow for their actual copy up to the space reserved by this slide;
    # all cards in a grid share the tallest required height for clean alignment.
    card_h=min(max_available,max(1.15,max(required,default=1.15)))
    for i, item in enumerate(elements):
        col,row=i%columns,i//columns
        card(slide,item,MARGIN+col*(card_w+gap),CONTENT_Y+row*(card_h+gap),card_w,card_h,d,i,emphasis=i==0)

def contact_matrix(slide, spec, d):
    """Use the full canvas for operational contact data with uneven lengths."""
    items=spec.elements[:6] or [SlideElement(heading="On-call escalation", body=clean_copy(spec.purpose))]
    count=len(items); columns=4 if count <= 4 else 3; rows=(count+columns-1)//columns
    gap=.22; width=(W-2*MARGIN-gap*(columns-1))/columns; height=(3.90-gap*(rows-1))/rows
    for index,item in enumerate(items):
        column=index%columns; row=index//columns
        x=MARGIN+column*(width+gap); y=2.18+row*(height+gap)
        add_surface(slide,x,y,width,height,d,emphasis=index==0)
        add_text(slide,f"{index+1:02d}",x+.20,y+.20,width-.40,.18,10,d.primary_color,True)
        heading=item.heading or item.label or "Escalation contact"
        add_text(slide,heading,x+.20,y+.56,width-.40,.58,text_size(heading,17,width-.40),d.text_primary,True,font=d.font_heading)
        add_text(slide,element_text(item),x+.20,y+1.24,width-.40,height-1.42,text_size(element_text(item),13,width-.40),d.text_secondary)

def workflow(slide, spec, d):
    """Connected flow stages with all copy contained in each stage surface."""
    items=spec.elements[:5]; n=max(1,len(items)); gap=.20 if n >= 5 else .28; width=(W-2*MARGIN-gap*(n-1))/n
    stage_y,stage_h=2.18,3.52
    for i, item in enumerate(items):
        x=MARGIN+i*(width+gap)
        add_surface(slide,x,stage_y,width,stage_h,d,emphasis=i==0)
        add_shape(slide,MSO_AUTO_SHAPE_TYPE.OVAL,x+.24,stage_y+.25,.46,.46,d.primary_color,d.primary_color)
        add_text(slide,f"{i+1:02d}",x+.24,stage_y+.39,.46,.14,9,d.background_color,True,align=PP_ALIGN.CENTER)
        if i<n-1:
            connector=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x+width+.03), Inches(stage_y+stage_h/2), Inches(x+width+gap-.03), Inches(stage_y+stage_h/2)); connector.line.color.rgb=rgb(d.primary_color); connector.line.width=Pt(1.5)
        heading_size=16 if n >= 5 else 20
        body_size=12 if n >= 5 else 15
        add_text(slide,item.heading or f"Step {i+1}",x+.18,stage_y+.95,width-.36,.78,text_size(item.heading or "",heading_size,width-.36),d.text_primary,True,align=PP_ALIGN.CENTER,font=d.font_heading)
        add_text(slide,element_text(item),x+.20,stage_y+1.94,width-.40,1.20,text_size(element_text(item),body_size,width-.40),d.text_secondary,align=PP_ALIGN.CENTER)

def chevron_flow(slide, spec, d):
    """A compact, connected process composition for an explicit workflow.

    Full-height chevrons look dramatic in a browser but introduce large
    diagonal dead areas in PowerPoint and leave too little usable text space.
    Keep the *flow* signal in small native arrow connectors and let every
    stage use a rectangular, readable text surface instead.
    """
    items=spec.elements[:5]; count=max(1,len(items)); gap=.20 if count >= 5 else .34; width=(W-2*MARGIN-gap*(count-1))/count
    stage_y,stage_h=2.25,3.42
    for index,item in enumerate(items):
        x=MARGIN+index*(width+gap)
        # A restrained top accent gives the variant its own visual language
        # without making a dark filled card the only readable stage.
        add_surface(slide,x,stage_y,width,stage_h,d,emphasis=index==0)
        add_shape(slide,MSO_AUTO_SHAPE_TYPE.RECTANGLE,x,stage_y,width,.10,d.primary_color,d.primary_color)
        add_shape(slide,MSO_AUTO_SHAPE_TYPE.OVAL,x+.26,stage_y+.28,.46,.46,d.primary_color,d.primary_color)
        add_text(slide,f"{index+1:02d}",x+.26,stage_y+.42,.46,.13,9,d.background_color,True,align=PP_ALIGN.CENTER)
        heading_size=16 if count >= 5 else 20
        body_size=12 if count >= 5 else 15
        add_text(slide,item.heading or f"Step {index+1}",x+.18,stage_y+1.02,width-.36,.74,text_size(item.heading or "",heading_size,width-.36),d.text_primary,True,align=PP_ALIGN.CENTER,font=d.font_heading)
        add_text(slide,element_text(item),x+.22,stage_y+2.02,width-.44,1.10,text_size(element_text(item),body_size,width-.44),d.text_secondary,align=PP_ALIGN.CENTER)
        if index<count-1:
            arrow=add_shape(slide,MSO_AUTO_SHAPE_TYPE.RIGHT_ARROW,x+width+.04,stage_y+stage_h/2-.16,gap-.08,.32,d.primary_color,d.primary_color)
            arrow.line.transparency=100

def cycle_loop(slide, spec, d):
    """Feedback loop diagram for recurring review, QA, and operating cycles."""
    items=spec.elements[:4]; node_w,node_h=2.45,1.08
    positions=((5.44,1.78),(8.55,3.40),(2.30,3.40),(5.44,5.02))[:len(items)]
    center_x,center_y=6.67,3.86
    # Join each stage to the next before adding nodes, which keeps the
    # connectors visually behind the labels and makes the feedback loop clear.
    centers=[(x+node_w/2,y+node_h/2) for x,y in positions]
    for start,end in zip(centers,centers[1:]+centers[:1],strict=False):
        connector=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(start[0]),Inches(start[1]),Inches(end[0]),Inches(end[1]))
        connector.line.color.rgb=rgb(d.primary_color); connector.line.width=Pt(1.5)
    # The loop centre is a visual anchor, not a place for a full sentence.
    # Keeping this fixed label prevents a slide purpose from colliding with
    # connectors or node copy when it spans multiple lines.
    add_shape(slide,MSO_AUTO_SHAPE_TYPE.OVAL,center_x-.92,center_y-.34,1.84,.68,shade(d.surface_color,10),d.primary_color)
    add_text(slide,"QA LOOP",center_x-.70,center_y-.08,1.40,.18,12,d.text_primary,True,align=PP_ALIGN.CENTER,font=d.font_heading)
    for index,(item,(x,y)) in enumerate(zip(items,positions,strict=False)):
        add_shape(slide,MSO_AUTO_SHAPE_TYPE.OVAL,x,y,node_w,node_h,shade(d.surface_color,8),d.primary_color)
        add_text(slide,item.heading or f"Cycle {index+1}",x+.18,y+.22,node_w-.36,.62,text_size(item.heading or "",13,node_w-.36),d.text_primary,True,align=PP_ALIGN.CENTER,font=d.font_heading)

def isometric_stack(slide, spec, d):
    """A 2.5D native architecture stack: editable and stable across viewers."""
    items=spec.elements[:4]
    count=max(1,len(items)); layer_h=min(1.34, (4.45-(count-1)*.10)/count)
    for index,item in enumerate(reversed(items)):
        y=5.95-(index+1)*layer_h-index*.10; inset=index*.30; width=9.25-index*.60
        x=2.03+inset
        add_shape(slide,MSO_AUTO_SHAPE_TYPE.PARALLELOGRAM,x,y,width,layer_h,shade(d.surface_color,12+index*5),d.primary_color)
        add_text(slide,item.heading or f"Layer {len(items)-index}",x+.48,y+.18,width-.96,.32,text_size(item.heading or "",18,width-.96),d.text_primary,True,align=PP_ALIGN.CENTER,font=d.font_heading)
        add_text(slide,element_text(item),x+.62,y+.62,width-1.24,layer_h-.76,text_size(element_text(item),13,width-1.24),d.text_secondary,align=PP_ALIGN.CENTER)

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
    count=max(1,len(items)); gap=.18; layer_h=(4.55-gap*(count-1))/count
    for i,item in enumerate(items):
        y=2.02+i*(layer_h+gap); inset=.28*i; x=MARGIN+inset; width=11.8-2*inset
        add_surface(slide,x,y,width,layer_h,d,emphasis=i==0)
        add_text(slide,item.heading or f"Layer {i+1}",x+.30,y+.18,width-.60,.30,text_size(item.heading or "",19,width-.60),d.primary_color,True,font=d.font_heading)
        if spec.visual_spec.get("nested_bullets"):
            add_bullets(slide,bullet_points(item,2),x+.36,y+.56,width-.72,layer_h-.70,d)
        else:
            add_text(slide,element_text(item),x+.32,y+.60,width-.64,layer_h-.76,text_size(element_text(item),15,width-.64),d.text_secondary)

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
    add_text(slide,"SLIDEWEAVER / BRIEF",MARGIN,1.12,3.0,.24,10,d.primary_color,True)
    add_text(slide,spec.title,MARGIN,1.62,text_width,2.60,cover_title_size(spec.title),d.header_color,True,font=d.font_heading)
    subtitle=spec.subtitle or spec.purpose
    add_text(slide,subtitle,MARGIN,4.58,7.2,.66,20,d.text_secondary)

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
    if spec.visual_spec.get("variable_rows"):
        items=spec.elements[:4]
        count=max(1,len(items)); gap=.16; row_h=(4.18-gap*(count-1))/count
        for index,item in enumerate(items):
            y=1.92+index*(row_h+gap)
            add_surface(slide,MARGIN,y,11.82,row_h,d,emphasis=index==0)
            add_text(slide,f"{index+1:02d}",MARGIN+.26,y+.28,.36,.16,10,d.primary_color,True)
            heading=item.heading or f"Node {index+1}"
            add_text(slide,heading,MARGIN+.86,y+.20,6.65,row_h-.36,text_size(heading,19,6.65),d.text_primary,True,font=d.font_heading)
            detail=element_text(item)
            if detail:
                add_text(slide,detail,MARGIN+7.72,y+.22,3.68,row_h-.38,text_size(detail,14,3.68),d.text_secondary)
        return
    items=spec.elements[:4]; count=max(1,len(items)); row_h=1.00 if count >= 4 else .94; gap=.15 if count >= 4 else .28
    for index,item in enumerate(items):
        y=CONTENT_Y+index*(row_h+gap)
        add_surface(slide,MARGIN,y,11.82,row_h,d,emphasis=index==0)
        add_text(slide,f"{index+1:02d}",MARGIN+.26,y+.32,.36,.16,10,d.primary_color,True)
        add_text(slide,item.heading or "Decision lens",MARGIN+.92,y+.20,4.1,.42,text_size(item.heading or "",18,4.1),d.text_primary,True,font=d.font_heading)
        add_text(slide,element_text(item),MARGIN+5.15,y+.23,5.98,.40,15,d.text_secondary)

def evidence_strip(slide, spec, d):
    items=spec.elements[:3]; count=max(1,len(items)); gap=.38; width=(W-2*MARGIN-gap*(count-1))/count
    for index,item in enumerate(items):
        x=MARGIN+index*(width+gap)
        add_shape(slide,MSO_AUTO_SHAPE_TYPE.RECTANGLE,x,CONTENT_Y,.08,3.62,d.primary_color,d.primary_color)
        add_text(slide,f"0{index+1}",x+.28,CONTENT_Y+.12,width-.28,.24,12,d.primary_color,True)
        if item.value:
            # Explicit user-supplied figures are evidence, not supporting
            # prose.  Give them the visual weight requested by a metrics
            # slide and keep the label/body inside the same measured lane.
            add_text(slide,str(item.value),x+.28,CONTENT_Y+.65,width-.38,.64,32,d.accent_color,True,font=d.font_heading)
            add_text(slide,item.heading or "Metric",x+.28,CONTENT_Y+1.44,width-.38,.56,18,d.text_primary,True,font=d.font_heading)
            supporting_copy=element_text(item)
            # Last-line defence: raw provider output can bypass a previous
            # QA pass during slide editing.  Never show a metric's numeric
            # value or its label twice in the supporting-copy lane.
            if supporting_copy.casefold() in {str(item.value).casefold(), (item.heading or "").casefold()}:
                supporting_copy=""
            if supporting_copy:
                add_text(slide,supporting_copy,x+.28,CONTENT_Y+2.18,width-.38,1.05,15,d.text_secondary)
            continue
        heading=item.heading or "Evidence"
        # A 26pt heading in a .65in box works for one line only.  Keynote
        # exposes that overflow rather than shrinking it, so allocate space
        # from the body lane before creating either text object.
        long_heading=len(clean_copy(heading))>24
        heading_height=1.18 if long_heading else .66
        heading_size=20 if long_heading else 24
        heading_y=CONTENT_Y+.72
        body_y=heading_y+heading_height+.16
        body_height=CONTENT_Y+3.62-body_y-.10
        add_text(slide,heading,x+.28,heading_y,width-.38,heading_height,text_size(heading,heading_size,width-.38),d.text_primary,True,font=d.font_heading)
        add_text(slide,element_text(item),x+.28,body_y,width-.38,body_height,16,d.text_secondary)

def native_table(slide, spec, d) -> bool:
    """Render explicit user data as an editable PowerPoint table.

    A markdown-looking table in a prompt is data, not a request for card
    copy.  Keeping it native makes it editable and guarantees headers/rows
    share one coordinate system in PowerPoint, Keynote, and the web preview.
    """
    raw=spec.visual_spec.get("table_data")
    if not isinstance(raw, dict):
        return False
    headers=raw.get("headers"); rows=raw.get("rows")
    if not isinstance(headers, list) or not headers or not isinstance(rows, list) or not rows:
        return False
    if any(not isinstance(row, list) or len(row) != len(headers) for row in rows):
        return False
    frame=slide.shapes.add_table(len(rows)+1, len(headers), Inches(MARGIN), Inches(1.78), Inches(W-2*MARGIN), Inches(4.72))
    table=frame.table
    total_width=W-2*MARGIN
    # Let the service-name and risk columns breathe, without allowing latency
    # labels to shrink into unreadable slivers.
    # Risk/decision text is human-readable prose, while latency is a compact
    # numeric value.  Allocate width accordingly so a word such as
    # "Priority" never leaves its final character on an orphan line.
    weights=[1.35, .75, .75, 1.55] if len(headers)==4 else [1.0]*len(headers)
    total_weight=sum(weights)
    for index, weight in enumerate(weights):
        table.columns[index].width=Inches(total_width*weight/total_weight)
    header_height=.62; row_height=(4.72-header_height)/len(rows)
    table.rows[0].height=Inches(header_height)
    for index in range(1,len(rows)+1): table.rows[index].height=Inches(row_height)
    for row_index, values in enumerate([headers,*rows]):
        for column_index, value in enumerate(values):
            cell=table.cell(row_index,column_index)
            cell.fill.solid(); cell.fill.fore_color.rgb=rgb(d.primary_color if row_index == 0 else shade(d.surface_color, 5 if row_index % 2 else 0))
            frame_text=cell.text_frame; frame_text.clear(); frame_text.word_wrap=True
            frame_text.margin_left=frame_text.margin_right=Inches(.05)
            frame_text.margin_top=frame_text.margin_bottom=Inches(.05)
            frame_text.vertical_anchor=MSO_ANCHOR.MIDDLE
            paragraph=frame_text.paragraphs[0]; paragraph.text=clean_copy(str(value)); paragraph.alignment=PP_ALIGN.LEFT
            width=total_width*weights[column_index]/total_weight-.18
            preferred=13 if row_index == 0 else (11 if len(paragraph.text) > 24 else 12)
            paragraph.font.size=Pt(fitted_text_size(paragraph.text,preferred,width,row_height-.10,bold=row_index==0,minimum=9))
            paragraph.font.bold=row_index==0; paragraph.font.name=d.font_body
            paragraph.font.color.rgb=rgb(d.background_color if row_index == 0 else d.text_primary)
    return True

def validated_chart_data(spec) -> tuple[list[str], list[tuple[str, list[float]]], str] | None:
    """Accept only explicit, comparable user-supplied series for native charts."""
    raw=spec.visual_spec.get("chart_data")
    if not isinstance(raw, dict): return None
    categories=raw.get("categories"); series=raw.get("series")
    if not isinstance(categories, list) or len(categories)<2 or not isinstance(series, list) or not series:
        return None
    labels=[str(value).strip() for value in categories]
    if not all(labels): return None
    normalized=[]
    for item in series[:3]:
        if not isinstance(item, dict) or not isinstance(item.get("values"), list) or len(item["values"]) != len(labels): return None
        try: values=[float(value) for value in item["values"]]
        except (TypeError, ValueError): return None
        if not all(value >= 0 for value in values): return None
        normalized.append((str(item.get("name") or "Series").strip() or "Series", values))
    return labels, normalized, str(raw.get("type") or "column").lower()

def native_chart(slide, spec, d) -> bool:
    """Add an editable PowerPoint chart only when factual chart data exists."""
    payload=validated_chart_data(spec)
    if not payload: return False
    categories, series, kind=payload
    chart_data=CategoryChartData(); chart_data.categories=categories
    for name, values in series: chart_data.add_series(name, values)
    chart_type=XL_CHART_TYPE.BAR_CLUSTERED if kind in {"bar", "bar_clustered"} else XL_CHART_TYPE.COLUMN_CLUSTERED
    frame=slide.shapes.add_chart(chart_type, Inches(MARGIN+.25), Inches(2.03), Inches(11.55), Inches(4.25), chart_data)
    chart=frame.chart; chart.has_legend=len(series)>1
    if chart.has_legend: chart.legend.position=XL_LEGEND_POSITION.BOTTOM
    chart.value_axis.has_major_gridlines=True
    chart.value_axis.tick_labels.font.size=Pt(11); chart.category_axis.tick_labels.font.size=Pt(11)
    plot=chart.plots[0]
    for index, chart_series in enumerate(plot.series):
        chart_series.format.fill.solid(); chart_series.format.fill.fore_color.rgb=rgb(d.primary_color if index == 0 else d.secondary_color)
        chart_series.format.line.color.rgb=rgb(d.primary_color if index == 0 else d.secondary_color)
    return True

def asymmetric_insight(slide, spec, d):
    purpose=clean_copy(spec.purpose)
    purpose_size=26 if len(purpose)>70 else 30
    # This lead can occupy several lines.  It is not constrained by the two
    # supporting cards, so reserve a real reading lane instead of clipping it.
    add_text(slide,purpose,MARGIN,CONTENT_Y+.18,5.0,2.24,purpose_size,d.text_primary,True,font=d.font_heading)
    for index,item in enumerate(spec.elements[:2]):
        y=CONTENT_Y+index*1.74
        card_height=1.55
        heading=item.heading or "Key point"
        add_surface(slide,6.3,y,6.25,card_height,d,emphasis=index==0)
        add_text(slide,heading,6.62,y+.24,5.55,.36,text_size(heading,20,5.55),d.primary_color,True,font=d.font_heading)
        # Bodies routinely need two or three lines.  Give them a fixed,
        # generous lane inside the surface rather than a .32in single line.
        add_text(slide,element_text(item),6.62,y+.72,5.55,.68,15,d.text_secondary)

def section_interlude(slide, spec, d):
    """Minimal breathing room between dense content sections."""
    depth_orb(slide,9.15,1.48,2.3,d)
    add_text(slide,"SECTION",MARGIN,1.55,2.0,.22,11,d.primary_color,True)
    add_text(slide,spec.title,MARGIN,2.00,7.4,1.15,text_size(spec.title,44,7.4),d.header_color,True,font=d.font_heading)
    add_text(slide,spec.subtitle or spec.purpose,MARGIN,3.35,6.7,.52,19,d.text_secondary,font=d.font_body)

def add_slide_transition(slide, transition_name: str | None):
    """Write a supported between-slide transition into PresentationML."""
    name=(transition_name or "fade").lower()
    if name not in {"fade", "push", "wipe"}: name="fade"
    transition=OxmlElement("p:transition")
    transition.set("spd", "med")
    transition.set("advClick", "1")
    effect=OxmlElement(f"p:{name}")
    if name in {"push", "wipe"}: effect.set("dir", "l")
    transition.append(effect)
    slide._element.insert_element_before(transition, "p:timing", "p:extLst")

def _timing_element(tag: str, **attributes):
    element=OxmlElement(tag)
    for key, value in attributes.items():
        element.set(key, str(value))
    return element

def _start_conditions(delay: str = "indefinite"):
    conditions=_timing_element("p:stCondLst")
    conditions.append(_timing_element("p:cond", delay=delay))
    return conditions

def _shape_ids_for_text(slide, value: str, used: set[int]) -> list[int]:
    """Resolve rendered text into component shape IDs without guessing order."""
    if not value:
        return []
    for shape in slide.shapes:
        if not getattr(shape, "has_text_frame", False) or shape.shape_id in used:
            continue
        if shape.text.strip() == clean_copy(value).strip():
            used.add(shape.shape_id)
            return [shape.shape_id]
    return []

def _animation_groups(slide, spec: SlideSpec) -> list[list[int]]:
    """Choose readable component groups, capped so slides never feel busy."""
    used: set[int]=set()
    groups=[]
    title=_shape_ids_for_text(slide, spec.title, used)
    if title:
        groups.append(title)
    if spec.layout_type.value == "title_slide":
        subtitle=_shape_ids_for_text(slide, spec.subtitle or spec.purpose, used)
        if subtitle:
            groups.append(subtitle)
        return groups[:2]
    for item in spec.elements[:3]:
        group=[]
        group.extend(_shape_ids_for_text(slide, item.heading or item.label or "", used))
        group.extend(_shape_ids_for_text(slide, element_text(item), used))
        if group:
            groups.append(group)
    return groups[:4]

def _entrance_filter(spec: SlideSpec) -> str:
    """Map narrative grammar to restrained native PowerPoint entrance effects."""
    layout=spec.layout_type.value
    stage=str(spec.visual_spec.get("story_stage", "")).lower()
    if spec.visual_spec.get("visual_variant") == "chevron_flow" or layout in {"step_workflow", "process_flow", "timeline"}:
        return "wipe(left)"
    if layout == "architecture_layers" or spec.visual_spec.get("visual_variant") == "isometric_stack":
        return "wipe(up)"
    if layout in {"comparison", "two_column"} or stage in {"decision lenses", "investor scenarios", "trade-offs"}:
        return "fade"
    if layout in {"key_metrics", "dashboard"} or stage in {"evidence", "outcome"}:
        return "fade"
    return "fade"

def add_component_animations(slide, spec: SlideSpec):
    """Attach click-to-reveal entrance effects to the slide's real components.

    `python-pptx` does not expose animations. This writes the standard
    PresentationML timing hierarchy directly, with every component group held
    behind one click. It deliberately animates text groups only: backgrounds,
    gradients, and decorative geometry stay stable across viewers.
    """
    groups=_animation_groups(slide, spec)
    if not groups or slide._element.find("p:timing", slide._element.nsmap) is not None:
        return
    timing=_timing_element("p:timing")
    timing_list=_timing_element("p:tnLst"); timing.append(timing_list)
    root_parallel=_timing_element("p:par"); timing_list.append(root_parallel)
    root=_timing_element("p:cTn", id="1", dur="indefinite", restart="never", nodeType="tmRoot")
    root_parallel.append(root)
    root_children=_timing_element("p:childTnLst"); root.append(root_children)
    sequence=_timing_element("p:seq", concurrent="1", nextAc="seek"); root_children.append(sequence)
    main=_timing_element("p:cTn", id="2", dur="indefinite", nodeType="mainSeq")
    sequence.append(main)
    main_children=_timing_element("p:childTnLst"); main.append(main_children)
    effect_filter=_entrance_filter(spec)
    next_id=3
    for group in groups:
        click_parallel=_timing_element("p:par"); main_children.append(click_parallel)
        click_node=_timing_element("p:cTn", id=str(next_id), fill="hold"); next_id+=1
        click_parallel.append(click_node); click_node.append(_start_conditions())
        click_children=_timing_element("p:childTnLst"); click_node.append(click_children)
        simultaneous=_timing_element("p:par"); click_children.append(simultaneous)
        simultaneous_node=_timing_element("p:cTn", id=str(next_id), fill="hold"); next_id+=1
        simultaneous.append(simultaneous_node); simultaneous_node.append(_start_conditions("0"))
        effects=_timing_element("p:childTnLst"); simultaneous_node.append(effects)
        for shape_id in group:
            effect=_timing_element("p:animEffect", transition="in", filter=effect_filter)
            effects.append(effect)
            behavior=_timing_element("p:cBhvr"); effect.append(behavior)
            behavior.append(_timing_element("p:cTn", id=str(next_id), dur="420", fill="hold")); next_id+=1
            target=_timing_element("p:tgtEl"); behavior.append(target)
            target.append(_timing_element("p:spTgt", spid=str(shape_id)))
    # OOXML order is transition then timing then extension list.
    slide._element.insert_element_before(timing, "p:extLst")

def build_presentation(spec: PresentationSpec, destination: str | Path) -> Path:
    prs=Presentation(); prs.slide_width=Inches(W); prs.slide_height=Inches(H); blank=prs.slide_layouts[6]; d=spec.design_system
    for spec_slide in spec.slides:
        slide=prs.slides.add_slide(blank); slide.background.fill.solid(); slide.background.fill.fore_color.rgb=rgb(d.background_color)
        apply_background_treatment(slide,spec_slide.visual_spec.get("background_treatment"),d)
        if spec_slide.layout_type.value=="title_slide": title_slide(slide,spec_slide,d)
        elif spec_slide.layout_type.value=="section_slide": section_interlude(slide,spec_slide,d)
        else:
            header(slide,spec_slide,d)
            layout=spec_slide.layout_type.value
            variant=spec_slide.visual_spec.get("visual_variant")
            if native_table(slide,spec_slide,d): pass
            elif native_chart(slide,spec_slide,d): pass
            elif spec_slide.visual_spec.get("image_path"): content_with_visual(slide,spec_slide,d)
            elif spec_slide.visual_spec.get("contact_matrix"): contact_matrix(slide,spec_slide,d)
            elif variant=="cycle_loop": cycle_loop(slide,spec_slide,d)
            elif variant=="chevron_flow": chevron_flow(slide,spec_slide,d)
            elif variant=="isometric_stack": isometric_stack(slide,spec_slide,d)
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
        add_component_animations(slide, spec_slide)
    path=Path(destination); path.parent.mkdir(parents=True,exist_ok=True); prs.save(path); return path
