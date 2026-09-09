"""Browser slide preview derived directly from the canonical PresentationSpec."""
from __future__ import annotations
import base64
import html
import mimetypes
from pathlib import Path
import textwrap
from app.schemas.presentation import PresentationSpec, SlideSpec
from app.rendering.layout_geometry import IMAGE_CONTENT, x_percent, y_percent

def esc(value: object) -> str: return html.escape(str(value or ""))
def body(element) -> str: return esc(element.body or element.subtext or element.value or "")

def image_data_url(path: str | None) -> str:
    if not path: return ""
    file=Path(path)
    if not file.exists(): return ""
    mime=mimetypes.guess_type(file.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(file.read_bytes()).decode()}"

def cards(slide: SlideSpec) -> str:
    return "".join(f'''<section class="card"><span class="index">{index+1:02d}</span><h3>{esc(item.heading or item.label or 'Key insight')}</h3><p>{body(item)}</p></section>''' for index,item in enumerate(slide.elements[:4]))

def render_slide_html(spec: PresentationSpec, slide_number: int) -> str:
    slide=spec.slides[slide_number-1]; d=spec.design_system; image=image_data_url(slide.visual_spec.get("image_path"))
    card_columns=min(3,max(1,len(slide.elements[:4])))
    visual_width=IMAGE_CONTENT["image"][0]+IMAGE_CONTENT["image"][2]-IMAGE_CONTENT["lead"][0]
    visual_height=IMAGE_CONTENT["image"][3]
    visual_copy_width=IMAGE_CONTENT["lead"][2]/visual_width*100
    visual_image_left=(IMAGE_CONTENT["image"][0]-IMAGE_CONTENT["lead"][0])/visual_width*100
    visual_image_width=IMAGE_CONTENT["image"][2]/visual_width*100
    visual_cards_top=(IMAGE_CONTENT["cards"][1]-IMAGE_CONTENT["lead"][1])/visual_height*100
    visual_card_height=IMAGE_CONTENT["card_height"]/visual_height*100
    visual_card_gap=IMAGE_CONTENT["card_gap"]/visual_height*100
    if slide.layout_type.value=="title_slide":
        content=f'''<div class="title-copy"><span class="eyebrow">DECKFORGE / BRIEF</span><h1>{esc(slide.title)}</h1><p>{esc(slide.subtitle or slide.purpose)}</p></div>{f'<img class="hero" src="{image}" />' if image else '<div class="orb"></div>'}'''
        kind="title"
    elif image:
        content=f'''<header><span class="eyebrow">{slide.slide_number:02d}</span><h2>{esc(slide.title)}</h2></header><div class="visual-layout"><div class="visual-copy"><strong>{esc(slide.purpose)}</strong><div class="visual-cards">{cards(slide)}</div></div><img class="content-image" src="{image}" /></div>'''; kind=""
    elif slide.layout_type.value=="two_column":
        groups=[]
        for i,item in enumerate(slide.elements[:2]):
            points=[p.strip(' •') for p in (item.body or '').replace('\\n','\n').split('\n') if p.strip()]
            groups.append(f"<section class='column'><span class='index'>{i+1:02d}</span><h3>{esc(item.heading)}</h3>"+"".join(f"<p>• {esc(point)}</p>" for point in points[:3])+"</section>")
        content=f"<header><span class='eyebrow'>{slide.slide_number:02d}</span><h2>{esc(slide.title)}</h2></header><div class='columns'>{''.join(groups)}</div>"; kind=""
    elif slide.layout_type.value=="comparison":
        rows="".join(f"<section class='compare-row'><span class='index'>{i+1:02d}</span><h3>{esc(item.heading or 'Decision lens')}</h3><p>{body(item)}</p></section>" for i,item in enumerate(slide.elements[:3]))
        content=f"<header><span class='eyebrow'>{slide.slide_number:02d} · DECISION LENSES</span><h2>{esc(slide.title)}</h2></header><div class='compare-rows'>{rows}</div>"; kind=""
    elif slide.layout_type.value=="key_metrics":
        metrics="".join(f"<section class='metric'><span>0{i+1}</span><h3>{esc(item.heading or 'Evidence')}</h3><p>{body(item)}</p></section>" for i,item in enumerate(slide.elements[:3]))
        content=f"<header><span class='eyebrow'>{slide.slide_number:02d}</span><h2>{esc(slide.title)}</h2></header><div class='metrics'>{metrics}</div>"; kind=""
    elif slide.layout_type.value=="content_with_visual":
        support="".join(f"<section class='support'><h3>{esc(item.heading or 'Key point')}</h3><p>{body(item)}</p></section>" for item in slide.elements[:2])
        content=f"<header><span class='eyebrow'>{slide.slide_number:02d}</span><h2>{esc(slide.title)}</h2></header><div class='asymmetric'><strong>{esc(slide.purpose)}</strong><div>{support}</div></div>"; kind=""
    else:
        content=f"<header><span class='eyebrow'>{slide.slide_number:02d}</span><h2>{esc(slide.title)}</h2>{f'<p class=subtitle>{esc(slide.subtitle)}</p>' if slide.subtitle else ''}</header><div class='cards'>{cards(slide)}</div>"; kind=""
    return textwrap.dedent(f'''<style>
      .deckforge-preview {{ box-sizing:border-box; aspect-ratio:16/9; width:100%; overflow:hidden; position:relative; padding:5.6% 6%; color:{d.text_primary}; background:{d.background_color}; font-family:{d.font_body},Arial,sans-serif; border-radius:14px; }}
      .deckforge-preview * {{ box-sizing:border-box; }} .deckforge-preview:before {{ content:''; position:absolute; inset:0 0 auto; height:7px; background:{d.primary_color}; }}
      header {{ position:relative; z-index:1; }} h1,h2,h3,p {{ margin:0; }} h1,h2,h3 {{ font-family:{d.font_heading},Arial,sans-serif; }} h2 {{ color:{d.header_color}; font-size:clamp(23px,3vw,42px); line-height:1.04; max-width:88%; }}
      .eyebrow,.index {{ color:{d.primary_color}; font-weight:800; font-size:11px; letter-spacing:.06em; }} .subtitle {{ color:{d.text_secondary}; margin-top:10px; }}
      .cards {{ display:grid; grid-template-columns:repeat({card_columns},1fr); gap:14px; margin-top:8%; }} .card,.column {{ background:linear-gradient(145deg,{d.surface_color},{d.background_color}); border:1px solid {d.primary_color}; border-radius:12px; padding:18px; min-height:205px; box-shadow:8px 10px 22px rgba(0,0,0,.38); }}
      .card h3,.column h3 {{ color:{d.primary_color}; font-size:clamp(16px,1.55vw,22px); margin:17px 0 12px; }} .card p,.column p {{ color:{d.text_secondary}; font-size:clamp(12px,1.1vw,16px); line-height:1.35; }}
      .columns {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-top:8%; }} .column p {{ margin:11px 0; }}
      .compare-rows {{ margin-top:5%; display:grid; gap:12px; }} .compare-row {{ display:grid; grid-template-columns:55px 30% 1fr; align-items:center; padding:16px 18px; border-radius:12px; background:linear-gradient(145deg,{d.surface_color},{d.background_color}); border:1px solid {d.primary_color}; box-shadow:8px 10px 22px rgba(0,0,0,.38); }} .compare-row h3 {{ color:{d.text_primary}; font-size:clamp(16px,1.65vw,23px); }} .compare-row p {{ color:{d.text_secondary}; font-size:clamp(12px,1.1vw,16px); }}
      .metrics {{ display:grid; grid-template-columns:repeat(3,1fr); gap:26px; margin-top:9%; }} .metric {{ border-left:6px solid {d.primary_color}; padding:12px 20px; min-height:220px; }} .metric span {{ color:{d.primary_color}; font-weight:800; font-size:13px; }} .metric h3 {{ font-size:clamp(18px,1.9vw,28px); margin:24px 0 14px; }} .metric p {{ color:{d.text_secondary}; font-size:clamp(12px,1.1vw,16px); line-height:1.4; }}
      .asymmetric {{ display:grid; grid-template-columns:.88fr 1.12fr; gap:42px; margin-top:9%; align-items:center; }} .asymmetric>strong {{ font-family:{d.font_heading}; font-size:clamp(23px,2.7vw,39px); line-height:1.05; }} .support {{ padding:17px 20px; margin-bottom:15px; border-radius:12px; background:linear-gradient(145deg,{d.surface_color},{d.background_color}); border:1px solid {d.primary_color}; box-shadow:8px 10px 22px rgba(0,0,0,.38); }} .support h3 {{ color:{d.primary_color}; font-size:clamp(16px,1.5vw,21px); margin-bottom:7px; }} .support p {{ color:{d.text_secondary}; font-size:clamp(12px,1.1vw,16px); }}
      .title {{ padding:9% 6%; }} .title:before {{ display:none; }} .title-copy {{ position:relative; z-index:2; width:61%; }} .title h1 {{ color:{d.header_color}; font-size:clamp(30px,5vw,66px); line-height:.98; margin:22px 0; }} .title p {{ color:{d.text_secondary}; font-size:clamp(15px,1.65vw,23px); line-height:1.35; }}
      .hero {{ position:absolute; right:5%; top:8%; height:84%; max-width:31%; object-fit:cover; border-left:7px solid {d.primary_color}; }} .orb {{ position:absolute; right:9%; top:16%; width:25%; aspect-ratio:1; border-radius:50%; background:radial-gradient(circle at 35% 35%,{d.primary_color},transparent 65%); opacity:.45; }}
      .visual-layout {{ position:absolute; left:{x_percent(IMAGE_CONTENT['lead'][0])}; top:{y_percent(IMAGE_CONTENT['lead'][1])}; width:{x_percent(visual_width)}; height:{y_percent(visual_height)}; }} .visual-copy {{ position:absolute; left:0; top:0; width:{visual_copy_width:.3f}%; height:100%; }} .visual-layout strong {{ display:block; width:100%; height:{IMAGE_CONTENT['lead'][3]/visual_height*100:.3f}%; font-size:clamp(17px,1.8vw,25px); line-height:1.08; }} .visual-cards {{ position:absolute; left:0; top:{visual_cards_top:.3f}%; width:100%; display:grid; gap:{visual_card_gap:.3f}%; }} .visual-cards .card {{ min-height:{visual_card_height:.3f}%; height:{visual_card_height:.3f}%; padding:11px 15px; }} .visual-cards .card h3 {{ margin:0 0 5px; }} .content-image {{ position:absolute; left:{visual_image_left:.3f}%; top:0; width:{visual_image_width:.3f}%; height:100%; object-fit:cover; border-radius:12px; border:1px solid {d.primary_color}; }}
    </style><article class="deckforge-preview {kind}">{content}</article>''').strip()
