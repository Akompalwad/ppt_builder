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

def mix(first: str, second: str, amount: float) -> str:
    """Mirror the opaque theme tint used by the PowerPoint renderer."""
    left=first.removeprefix("#"); right=second.removeprefix("#")
    channels=[]
    for index in (0,2,4):
        start=int(left[index:index+2],16); end=int(right[index:index+2],16)
        channels.append(round(start+(end-start)*max(0,min(1,amount))))
    return "#"+"".join(f"{channel:02X}" for channel in channels)

def image_data_url(path: str | None) -> str:
    if not path: return ""
    file=Path(path)
    if not file.exists(): return ""
    mime=mimetypes.guess_type(file.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(file.read_bytes()).decode()}"

def cards(slide: SlideSpec) -> str:
    return "".join(f'''<section class="card"><span class="index">{index+1:02d}</span><h3>{esc(item.heading or item.label or 'Key insight')}</h3><p>{body(item)}</p></section>''' for index,item in enumerate(slide.elements[:4]))

def chart_markup(slide: SlideSpec) -> str:
    """Browser equivalent of the native chart, without inventing values."""
    raw=slide.visual_spec.get("chart_data")
    if not isinstance(raw,dict) or not isinstance(raw.get("categories"),list) or len(raw["categories"])<2: return ""
    series=raw.get("series")
    if not isinstance(series,list) or not series or not isinstance(series[0],dict): return ""
    values=series[0].get("values")
    if not isinstance(values,list) or len(values)!=len(raw["categories"]): return ""
    try: numeric=[float(value) for value in values]
    except (TypeError,ValueError): return ""
    maximum=max(numeric,default=0)
    if maximum<=0: return ""
    bars="".join(f"<section class='chart-bar'><span style='height:{value/maximum*100:.2f}%'></span><small>{esc(label)}</small><b>{value:g}</b></section>" for label,value in zip(raw["categories"],numeric,strict=True))
    return f"<div class='native-chart-preview'><strong>{esc(series[0].get('name') or 'Source data')}</strong><div class='chart-bars'>{bars}</div></div>"

def background_css(slide: SlideSpec, d) -> str:
    """Mirror the portable PowerPoint gradient with restrained CSS layers."""
    treatment=str(slide.visual_spec.get("background_treatment") or "clean").lower()
    if treatment=="halo":
        return f"linear-gradient(90deg, {d.background_color} 0 61%, {mix(d.background_color,d.primary_color,.12)} 100%)"
    if treatment=="diagonal":
        return f"linear-gradient(135deg, {d.background_color} 0 64%, {mix(d.background_color,d.primary_color,.09)} 100%)"
    if treatment=="spotlight":
        return f"linear-gradient(315deg, {d.background_color} 0 52%, {mix(d.background_color,d.primary_color,.13)} 100%)"
    if treatment=="blueprint":
        return f"linear-gradient(135deg, {d.background_color}, {mix(d.background_color,d.primary_color,.08)})"
    return d.background_color

def render_slide_html(spec: PresentationSpec, slide_number: int) -> str:
    slide=spec.slides[slide_number-1]; d=spec.design_system; image=image_data_url(slide.visual_spec.get("image_path"))
    background=background_css(slide,d)
    # Keep grid geometry identical to the editable PPTX renderer: four
    # capabilities are a balanced 2×2, not three cards plus an orphan row.
    card_count=len(slide.elements[:4])
    card_columns=2 if card_count in (2,4) else min(3,max(1,card_count))
    visual_width=IMAGE_CONTENT["image"][0]+IMAGE_CONTENT["image"][2]-IMAGE_CONTENT["lead"][0]
    visual_height=IMAGE_CONTENT["image"][3]
    visual_copy_width=IMAGE_CONTENT["lead"][2]/visual_width*100
    visual_image_left=(IMAGE_CONTENT["image"][0]-IMAGE_CONTENT["lead"][0])/visual_width*100
    visual_image_width=IMAGE_CONTENT["image"][2]/visual_width*100
    visual_cards_top=(IMAGE_CONTENT["cards"][1]-IMAGE_CONTENT["lead"][1])/visual_height*100
    visual_card_height=IMAGE_CONTENT["card_height"]/visual_height*100
    visual_card_gap=IMAGE_CONTENT["card_gap"]/visual_height*100
    if slide.layout_type.value=="title_slide":
        content=f'''<div class="title-copy"><span class="eyebrow">SLIDEWEAVER / BRIEF</span><h1>{esc(slide.title)}</h1><p>{esc(slide.subtitle or slide.purpose)}</p></div>{f'<img class="hero" src="{image}" />' if image else '<div class="orb"></div>'}'''
        kind="title"
    elif chart:=chart_markup(slide):
        content=f"<header><span class='eyebrow'>{slide.slide_number:02d}</span><h2>{esc(slide.title)}</h2></header>{chart}"; kind=""
    elif image:
        content=f'''<header><span class="eyebrow">{slide.slide_number:02d}</span><h2>{esc(slide.title)}</h2></header><div class="visual-layout"><div class="visual-copy"><strong>{esc(slide.purpose)}</strong><div class="visual-cards">{cards(slide)}</div></div><img class="content-image" src="{image}" /></div>'''; kind=""
    elif slide.visual_spec.get("visual_variant")=="chevron_flow":
        steps="".join(f"<section class='flow-step'><div class='chevron'><span>{i+1:02d}</span><h3>{esc(item.heading or f'Step {i+1}')}</h3><p>{body(item)}</p></div></section>" for i,item in enumerate(slide.elements[:4]))
        content=f"<header><span class='eyebrow'>{slide.slide_number:02d}</span><h2>{esc(slide.title)}</h2></header><div class='chevrons'>{steps}</div>"; kind=""
    elif slide.visual_spec.get("visual_variant")=="cycle_loop":
        nodes="".join(f"<section class='cycle-node node-{i+1}'><h3>{esc(item.heading or f'Stage {i+1}')}</h3></section>" for i,item in enumerate(slide.elements[:4]))
        content=f"<header><span class='eyebrow'>{slide.slide_number:02d}</span><h2>{esc(slide.title)}</h2></header><div class='cycle'><strong>{esc(slide.purpose)}</strong>{nodes}</div>"; kind=""
    elif slide.visual_spec.get("visual_variant")=="isometric_stack":
        layers="".join(f"<section class='iso-layer'><h3>{esc(item.heading or 'Layer')}</h3><p>{body(item)}</p></section>" for item in reversed(slide.elements[:4]))
        content=f"<header><span class='eyebrow'>{slide.slide_number:02d}</span><h2>{esc(slide.title)}</h2></header><div class='iso-stack'>{layers}</div>"; kind=""
    elif slide.layout_type.value=="architecture_layers":
        layers="".join(f"<section class='architecture-layer layer-{i+1}'><h3>{esc(item.heading or f'Layer {i+1}')}</h3><p>{body(item)}</p></section>" for i,item in enumerate(slide.elements[:4]))
        content=f"<header><span class='eyebrow'>{slide.slide_number:02d}</span><h2>{esc(slide.title)}</h2></header><div class='architecture-layers'>{layers}</div>"; kind=""
    elif slide.layout_type.value in {"step_workflow", "process_flow", "timeline"}:
        stages="".join(f"<section class='standard-flow-stage'><span>{i+1:02d}</span><h3>{esc(item.heading or f'Step {i+1}')}</h3><p>{body(item)}</p></section>" for i,item in enumerate(slide.elements[:4]))
        content=f"<header><span class='eyebrow'>{slide.slide_number:02d}</span><h2>{esc(slide.title)}</h2></header><div class='standard-flow'>{stages}</div>"; kind=""
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
      .slideweaver-preview {{ box-sizing:border-box; aspect-ratio:16/9; width:100%; max-width:1120px; margin:0 auto; overflow:hidden; position:relative; padding:5.6% 6%; color:{d.text_primary}; background:{background}; font-family:{d.font_body},Arial,sans-serif; border-radius:14px; }}
      .slideweaver-preview * {{ box-sizing:border-box; }} .slideweaver-preview:before {{ content:''; position:absolute; inset:0 0 auto; height:7px; background:{d.primary_color}; }}
      header {{ position:relative; z-index:1; }} h1,h2,h3,p {{ margin:0; }} h1,h2,h3 {{ font-family:{d.font_heading},Arial,sans-serif; }} h2 {{ color:{d.header_color}; font-size:clamp(23px,3vw,42px); line-height:1.04; max-width:88%; }}
      .eyebrow,.index {{ color:{d.primary_color}; font-weight:800; font-size:11px; letter-spacing:.06em; }} .subtitle {{ color:{d.text_secondary}; margin-top:10px; }}
      .cards {{ display:grid; grid-template-columns:repeat({card_columns},1fr); gap:14px; margin-top:8%; }} .card,.column {{ background:linear-gradient(145deg,{d.surface_color},{d.background_color}); border:1px solid {d.primary_color}; border-radius:12px; padding:18px; min-height:205px; box-shadow:8px 10px 22px rgba(0,0,0,.38); }}
      .card h3,.column h3 {{ color:{d.primary_color}; font-size:clamp(16px,1.55vw,22px); margin:17px 0 12px; }} .card p,.column p {{ color:{d.text_secondary}; font-size:clamp(12px,1.1vw,16px); line-height:1.35; }}
      .columns {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-top:8%; }} .column p {{ margin:11px 0; }}
      .compare-rows {{ margin-top:5%; display:grid; gap:12px; }} .compare-row {{ display:grid; grid-template-columns:55px 30% 1fr; align-items:center; padding:16px 18px; border-radius:12px; background:linear-gradient(145deg,{d.surface_color},{d.background_color}); border:1px solid {d.primary_color}; box-shadow:8px 10px 22px rgba(0,0,0,.38); }} .compare-row h3 {{ color:{d.text_primary}; font-size:clamp(16px,1.65vw,23px); }} .compare-row p {{ color:{d.text_secondary}; font-size:clamp(12px,1.1vw,16px); }}
      .metrics {{ display:grid; grid-template-columns:repeat(3,1fr); gap:26px; margin-top:9%; }} .metric {{ border-left:6px solid {d.primary_color}; padding:12px 20px; min-height:220px; }} .metric span {{ color:{d.primary_color}; font-weight:800; font-size:13px; }} .metric h3 {{ font-size:clamp(18px,1.9vw,28px); margin:24px 0 14px; }} .metric p {{ color:{d.text_secondary}; font-size:clamp(12px,1.1vw,16px); line-height:1.4; }}
      .native-chart-preview {{ margin:8% 3% 0; height:52%; border-bottom:1px solid {d.primary_color}; }} .native-chart-preview>strong {{ color:{d.text_secondary}; font-size:13px; }} .chart-bars {{ height:82%; display:flex; align-items:end; justify-content:space-around; gap:8%; padding-top:5%; }} .chart-bar {{ height:100%; flex:1; display:flex; flex-direction:column; align-items:center; justify-content:end; gap:5px; }} .chart-bar span {{ display:block; width:54%; background:{d.primary_color}; border-radius:6px 6px 0 0; }} .chart-bar small {{ color:{d.text_secondary}; text-align:center; }} .chart-bar b {{ color:{d.text_primary}; font-size:12px; }}
      .asymmetric {{ display:grid; grid-template-columns:.88fr 1.12fr; gap:42px; margin-top:9%; align-items:center; }} .asymmetric>strong {{ font-family:{d.font_heading}; font-size:clamp(23px,2.7vw,39px); line-height:1.05; }} .support {{ padding:17px 20px; margin-bottom:15px; border-radius:12px; background:linear-gradient(145deg,{d.surface_color},{d.background_color}); border:1px solid {d.primary_color}; box-shadow:8px 10px 22px rgba(0,0,0,.38); }} .support h3 {{ color:{d.primary_color}; font-size:clamp(16px,1.5vw,21px); margin-bottom:7px; }} .support p {{ color:{d.text_secondary}; font-size:clamp(12px,1.1vw,16px); }}
      .chevrons {{ display:grid; grid-template-columns:repeat({min(4,max(1,len(slide.elements[:4])))},1fr); gap:7px; margin-top:8%; }} .flow-step {{ min-width:0; }} .chevron {{ min-height:310px; height:310px; padding:22px 21px; clip-path:polygon(0 0,88% 0,100% 50%,88% 100%,0 100%,12% 50%); background:{d.surface_color}; border:1px solid {d.primary_color}; text-align:center; }} .flow-step:first-child .chevron {{ background:{d.primary_color}; color:{d.background_color}; }} .chevron span {{ display:block; font-weight:800; font-size:11px; text-align:left; }} .chevron h3 {{ margin:25px 6px 20px; font-size:clamp(13px,1.25vw,18px); }} .chevron p {{ color:{d.text_secondary}; font-size:clamp(11px,1vw,14px); line-height:1.32; }} .flow-step:first-child .chevron p {{ color:{mix(d.background_color,d.text_primary,.78)}; }}
      .standard-flow {{ display:grid; grid-template-columns:repeat({min(4,max(1,len(slide.elements[:4])))},1fr); gap:18px; margin-top:8%; }} .standard-flow-stage {{ min-height:310px; position:relative; padding:24px 20px; border:1px solid {d.primary_color}; border-radius:12px; background:linear-gradient(145deg,{d.surface_color},{d.background_color}); text-align:center; box-shadow:7px 9px 18px rgba(0,0,0,.2); }} .standard-flow-stage:not(:last-child):after {{ content:'›'; position:absolute; right:-17px; top:43%; z-index:2; color:{d.primary_color}; font-size:30px; font-weight:800; }} .standard-flow-stage span {{ display:grid; place-items:center; width:30px; height:30px; border-radius:50%; background:{d.primary_color}; color:{d.background_color}; font-size:11px; font-weight:800; }} .standard-flow-stage h3 {{ margin:31px 0 20px; font-size:clamp(14px,1.4vw,20px); }} .standard-flow-stage p {{ color:{d.text_secondary}; font-size:clamp(11px,1vw,14px); line-height:1.35; }}
      .architecture-layers {{ display:grid; gap:12px; margin:7% auto 0; width:86%; }} .architecture-layer {{ min-height:78px; padding:14px 24px; border:1px solid {d.primary_color}; border-radius:10px; background:linear-gradient(145deg,{d.surface_color},{d.background_color}); }} .architecture-layer:nth-child(2) {{ margin:0 3%; }} .architecture-layer:nth-child(3) {{ margin:0 6%; }} .architecture-layer:nth-child(4) {{ margin:0 9%; }} .architecture-layer h3 {{ color:{d.primary_color}; font-size:clamp(15px,1.55vw,22px); margin-bottom:7px; }} .architecture-layer p {{ color:{d.text_secondary}; font-size:clamp(11px,1vw,15px); line-height:1.32; }}
      .cycle {{ position:relative; width:58%; aspect-ratio:1.45; margin:5% auto 0; }} .cycle>strong,.cycle-node {{ position:absolute; display:grid; place-items:center; text-align:center; border:1px solid {d.primary_color}; border-radius:50%; }} .cycle>strong {{ inset:31% 32%; padding:10px; background:{d.surface_color}; font-size:clamp(12px,1.2vw,17px); }} .cycle-node {{ width:30%; aspect-ratio:1; padding:10px; background:{d.surface_color}; }} .cycle-node h3 {{ font-size:clamp(12px,1.2vw,17px); color:{d.text_primary}; }} .node-1 {{ left:35%; top:0; }} .node-2 {{ right:0; top:35%; }} .node-3 {{ left:0; top:35%; }} .node-4 {{ left:35%; bottom:0; }}
      .iso-stack {{ width:68%; margin:10% auto 0; }} .iso-layer {{ transform:skewX(-16deg); border:1px solid {d.primary_color}; background:{d.surface_color}; padding:15px 32px; margin-top:-2px; }} .iso-layer>* {{ transform:skewX(16deg); }} .iso-layer h3 {{ font-size:clamp(15px,1.5vw,22px); }} .iso-layer p {{ color:{d.text_secondary}; font-size:clamp(11px,1vw,15px); }}
      .title {{ padding:9% 6%; }} .title:before {{ display:none; }} .title-copy {{ position:relative; z-index:2; width:61%; }} .title h1 {{ color:{d.header_color}; font-size:clamp(30px,5vw,66px); line-height:.98; margin:22px 0; }} .title p {{ color:{d.text_secondary}; font-size:clamp(15px,1.65vw,23px); line-height:1.35; }}
      .hero {{ position:absolute; right:5%; top:8%; height:84%; max-width:31%; object-fit:cover; border-left:7px solid {d.primary_color}; }} .orb {{ position:absolute; right:9%; top:16%; width:25%; aspect-ratio:1; border-radius:50%; background:linear-gradient(315deg,{mix(d.background_color,d.primary_color,.28)},{mix(d.background_color,d.primary_color,.025)}); }}
      .visual-layout {{ position:absolute; left:{x_percent(IMAGE_CONTENT['lead'][0])}; top:{y_percent(IMAGE_CONTENT['lead'][1])}; width:{x_percent(visual_width)}; height:{y_percent(visual_height)}; }} .visual-copy {{ position:absolute; left:0; top:0; width:{visual_copy_width:.3f}%; height:100%; }} .visual-layout strong {{ display:block; width:100%; height:{IMAGE_CONTENT['lead'][3]/visual_height*100:.3f}%; font-size:clamp(17px,1.8vw,25px); line-height:1.08; }} .visual-cards {{ position:absolute; left:0; top:{visual_cards_top:.3f}%; width:100%; display:grid; gap:{visual_card_gap:.3f}%; }} .visual-cards .card {{ min-height:{visual_card_height:.3f}%; height:{visual_card_height:.3f}%; padding:11px 15px; }} .visual-cards .card h3 {{ margin:0 0 5px; }} .content-image {{ position:absolute; left:{visual_image_left:.3f}%; top:0; width:{visual_image_width:.3f}%; height:100%; object-fit:cover; border-radius:12px; border:1px solid {d.primary_color}; }}
    </style><article class="slideweaver-preview {kind}">{content}</article>''').strip()
