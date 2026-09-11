"""Topic-specific presentation visual generation, isolated from the LLM gateway."""
from __future__ import annotations
import base64
from pathlib import Path
import httpx
from app.config import get_settings
from app.schemas.presentation import PresentationSpec

class ImageService:
    def __init__(self): self.settings=get_settings()

    def status(self) -> dict:
        """Return safe, actionable image configuration diagnostics.

        This deliberately reports configuration state rather than an access key
        or a network probe, so opening the Streamlit page never consumes an
        Unsplash request. The generation record captures actual request
        results once a deck is created.
        """
        provider=self.settings.image_provider.lower().strip()
        if provider == "unsplash":
            return {
                "provider":"unsplash",
                "ready":bool(self.settings.unsplash_access_key),
                "message":"Unsplash is ready for the next deck." if self.settings.unsplash_access_key else "Unsplash is selected, but UNSPLASH_ACCESS_KEY is missing from the API server environment.",
            }
        if provider == "openai":
            return {
                "provider":"openai",
                "ready":bool(self.settings.image_api_key),
                "message":"The image provider is ready for the next deck." if self.settings.image_api_key else "The image provider is selected, but IMAGE_API_KEY is missing from the API server environment.",
            }
        return {"provider":provider or "none", "ready":False, "message":"No supported image provider is configured."}

    def _prompt(self, spec: PresentationSpec, slide_number: int) -> str:
        slide=spec.slides[slide_number-1]; supplied=slide.visual_spec.get("image_prompt")
        if supplied: return str(supplied)
        return (f"Premium editorial PowerPoint visual about {spec.topic}. Slide intent: {slide.purpose}. "
                f"Audience: {spec.target_audience}. Use a cohesive {spec.theme} palette. No text, logos, watermark, UI, or people unless essential.")

    def _generate_openai(self, prompt: str, destination: Path) -> None:
        if not self.settings.image_api_key: raise RuntimeError("IMAGE_API_KEY is not configured")
        response=httpx.post(f"{self.settings.image_base_url.rstrip('/')}/images/generations",headers={"Authorization":f"Bearer {self.settings.image_api_key}"},json={"model":self.settings.image_model,"prompt":prompt,"size":"1536x1024","quality":"medium","n":1},timeout=120)
        response.raise_for_status(); encoded=response.json()["data"][0]["b64_json"]
        destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(base64.b64decode(encoded))

    def _generate_unsplash(self, spec: PresentationSpec, slide_number: int, destination: Path) -> dict:
        if not self.settings.unsplash_access_key: raise RuntimeError("UNSPLASH_ACCESS_KEY is not configured")
        slide=spec.slides[slide_number-1]
        # Models can omit a stock query, especially when the user supplied a
        # detailed slide contract. A title-led fallback stays specific enough
        # for Unsplash and avoids one generic image across every deck.
        query=str(slide.visual_spec.get("stock_query") or f"{slide.title} {spec.topic}").strip()
        headers={"Authorization":f"Client-ID {self.settings.unsplash_access_key}"}
        response=httpx.get(f"{self.settings.unsplash_base_url.rstrip('/')}/search/photos",params={"query":query,"per_page":12,"orientation":"landscape","content_filter":"high"},headers=headers,timeout=30)
        response.raise_for_status(); results=response.json().get("results",[])
        if not results: raise RuntimeError("Unsplash returned no matching images")
        item=results[(slide_number-1) % len(results)]
        image_url=item["urls"]["regular"]
        image=httpx.get(image_url,timeout=60); image.raise_for_status()
        destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(image.content)
        # Register the download with Unsplash while retaining provenance for the deck.
        if item.get("links",{}).get("download_location"):
            try: httpx.get(item["links"]["download_location"],headers=headers,timeout=15)
            except httpx.HTTPError: pass
        return {"query":query,"source":"Unsplash","source_url":item.get("links",{}).get("html"),"license":"Unsplash License","photographer":item.get("user",{}).get("name"),"photographer_url":item.get("user",{}).get("links",{}).get("html")}

    def attach_assets(self, spec: PresentationSpec, asset_dir: Path, enabled: bool) -> list[dict]:
        """Generate a hero plus only slides explicitly marked image_required by the visual director."""
        if not enabled: return [{"status":"skipped","reason":"User did not enable topic-specific visuals"}]
        provider=self.settings.image_provider.lower()
        if provider not in {"openai","unsplash"}:
            return [{"status":"skipped","reason":"IMAGE_PROVIDER is not configured"}]
        configuration=self.status()
        if not configuration["ready"]:
            return [{"status":"skipped","reason":configuration["message"]}]
        targets=[1]
        targets.extend(s.slide_number for s in spec.slides[1:] if s.visual_spec.get("image_required") is True)
        targets=list(dict.fromkeys(targets))[:self.settings.max_generated_images_per_deck]
        results=[]
        for number in targets:
            path=asset_dir / f"slide-{number}-visual.{'jpg' if provider == 'unsplash' else 'png'}"
            try:
                provenance=self._generate_unsplash(spec,number,path) if provider=="unsplash" else {"source":"AI-generated"}
                if provider=="openai": self._generate_openai(self._prompt(spec,number),path)
                spec.slides[number-1].visual_spec["image_path"]=str(path)
                spec.slides[number-1].visual_spec["asset_metadata"]=provenance
                results.append({"slide_number":number,"status":"generated","path":str(path),**provenance})
            except Exception as exc:
                # Surface actionable diagnostics in the UI; a missing image
                # should not silently collapse every cover to the same fallback.
                results.append({"slide_number":number,"status":"failed","reason":f"{type(exc).__name__}: {str(exc)[:140]}"})
        return results

    def attach_slide_asset(self, spec: PresentationSpec, slide_number: int, asset_dir: Path) -> dict:
        """Attach one requested edit image without regenerating the deck cover."""
        provider=self.settings.image_provider.lower()
        if provider not in {"openai", "unsplash"}:
            return {"slide_number":slide_number,"status":"skipped","reason":"IMAGE_PROVIDER is not configured"}
        configuration=self.status()
        if not configuration["ready"]:
            return {"slide_number":slide_number,"status":"skipped","reason":configuration["message"]}
        suffix="jpg" if provider=="unsplash" else "png"
        path=asset_dir/f"slide-{slide_number}-edit-visual.{suffix}"
        try:
            provenance=self._generate_unsplash(spec,slide_number,path) if provider=="unsplash" else {"source":"AI-generated"}
            if provider=="openai": self._generate_openai(self._prompt(spec,slide_number),path)
            slide=spec.slides[slide_number-1]
            slide.visual_spec["image_path"]=str(path)
            slide.visual_spec["asset_metadata"]=provenance
            slide.visual_spec.pop("edit_image_requested",None)
            return {"slide_number":slide_number,"status":"generated","path":str(path),**provenance}
        except Exception as exc:
            return {"slide_number":slide_number,"status":"failed","reason":f"{type(exc).__name__}: {str(exc)[:140]}"}
