"""Provider-routed image generation for QonQrete.

Routing:
  * OpenAI/Codex -> internal Codex route first, then OpenAI Images API.
  * Gemini -> Google GenAI/Imagen-compatible Gemini image model.
  * everything else -> public Hugging Face FLUX Gradio Space.

No Venice detection or dependency exists in this module.
"""
from __future__ import annotations
import base64, dataclasses, json, os, shutil, subprocess, tempfile, time, urllib.request, urllib.error
from typing import Any, Dict, Optional
from .config import resolve_config

@dataclasses.dataclass
class ImageGenRequest:
    prompt: str
    model: str = "auto"
    aspect_ratio: str = "1:1"
    resolution: str = "1K"
    width: int = 0
    height: int = 0
    quality: str = ""
    format: str = "png"
    cfg_scale: float = 7.5
    steps: int = 20
    seed: int = 0
    safe_mode: bool = False
    hide_watermark: bool = False
    embed_exif_metadata: bool = False
    negative_prompt: str = ""
    style: str = ""
    return_binary: bool = True

@dataclasses.dataclass
class ImageGenResult:
    success: bool
    image_data: Optional[bytes] = None
    image_path: Optional[str] = None
    request_id: str = ""
    model_used: str = ""
    format: str = "png"
    duration_ms: float = 0.0
    error: str = ""
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    @property
    def base64(self): return base64.b64encode(self.image_data).decode() if self.image_data else ""

def _save(data: bytes, path: str) -> ImageGenResult:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path,"wb") as f: f.write(data)
    return ImageGenResult(True, data, path, format=os.path.splitext(path)[1].lstrip(".") or "png")

def _dims(req):
    if req.width and req.height: return req.width, req.height
    ratios={"1:1":(1,1),"16:9":(16,9),"9:16":(9,16),"4:3":(4,3),"3:4":(3,4),"3:2":(3,2),"2:3":(2,3)}
    rw,rh=ratios.get(req.aspect_ratio,(1,1))
    long_side={"1K":1024,"2K":2048,"4K":4096}.get(req.resolution,1024)
    return (long_side,round(long_side*rh/rw)) if rw>=rh else (round(long_side*rw/rh),long_side)

def _openai(req, output_path):
    t=time.time()
    key=os.environ.get("OPENAI_API_KEY","").strip()
    # Preferred Codex route: let the installed Codex CLI use its normal OpenAI
    # session/tooling when available. The prompt asks for a concrete file artifact.
    codex=shutil.which("codex")
    if codex:
        out=os.path.abspath(output_path)
        prompt=(f"Generate an image for this request: {req.prompt}. Save the final image "
                f"as {out}. Do not merely describe it; create the file. Aspect ratio "
                f"{req.aspect_ratio}, resolution {req.resolution}.")
        try:
            r=subprocess.run([codex,"exec","--full-auto",prompt],capture_output=True,text=True,timeout=240)
            if r.returncode==0 and os.path.isfile(out):
                return ImageGenResult(True,open(out,"rb").read(),out,model_used=req.model or "codex",format=req.format,duration_ms=(time.time()-t)*1000,
                                      metadata={"route":"codex"})
        except Exception:
            pass
    if not key:
        return ImageGenResult(False,error="OpenAI image generation requires codex authentication or OPENAI_API_KEY.")
    model=req.model if req.model!="auto" else "gpt-image-1"
    payload={"model":model,"prompt":req.prompt,"size":"1024x1024","quality":req.quality or "auto","n":1}
    w,h=_dims(req)
    if w/h > 1.5: payload["size"]="1536x1024"
    elif h/w > 1.5: payload["size"]="1024x1536"
    data=json.dumps(payload).encode()
    request=urllib.request.Request("https://api.openai.com/v1/images/generations",data=data,
        headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(request,timeout=180) as resp: obj=json.loads(resp.read())
        item=obj["data"][0]
        raw=base64.b64decode(item["b64_json"]) if item.get("b64_json") else urllib.request.urlopen(item["url"],timeout=120).read()
        res=_save(raw,output_path); res.model_used=model; res.duration_ms=(time.time()-t)*1000; res.metadata={"route":"openai-images"}
        return res
    except Exception as e:
        return ImageGenResult(False,error=f"OpenAI image generation failed: {e}",duration_ms=(time.time()-t)*1000)

def _gemini(req, output_path):
    t=time.time(); key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    model=req.model if req.model!="auto" else "gemini-2.5-flash-image"
    try:
        from google import genai
        from google.genai import types
        client=genai.Client(api_key=key) if key else genai.Client()
        response=client.models.generate_content(model=model,contents=req.prompt,
            config=types.GenerateContentConfig(response_modalities=["TEXT","IMAGE"]))
        for cand in getattr(response,"candidates",[]) or []:
            for part in getattr(getattr(cand,"content",None),"parts",[]) or []:
                inline=getattr(part,"inline_data",None)
                if inline and getattr(inline,"data",None):
                    res=_save(inline.data,output_path); res.model_used=model; res.duration_ms=(time.time()-t)*1000; res.metadata={"route":"google-genai-sdk"}; return res
        raise RuntimeError("Google GenAI returned no inline image data")
    except ImportError:
        pass
    except Exception as e:
        return ImageGenResult(False,error=f"Google GenAI image generation failed: {e}",duration_ms=(time.time()-t)*1000)
    if not key: return ImageGenResult(False,error="Gemini image generation requires google-genai and GEMINI_API_KEY/GOOGLE_API_KEY.")
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload={"contents":[{"parts":[{"text":req.prompt}]}],"generationConfig":{"responseModalities":["TEXT","IMAGE"]}}
    try:
        q=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
        with urllib.request.urlopen(q,timeout=180) as resp: obj=json.loads(resp.read())
        for cand in obj.get("candidates",[]):
            for part in cand.get("content",{}).get("parts",[]):
                d=part.get("inlineData") or part.get("inline_data")
                if d and d.get("data"):
                    res=_save(base64.b64decode(d["data"]),output_path); res.model_used=model; res.duration_ms=(time.time()-t)*1000; res.metadata={"route":"google-genai-rest"}; return res
        raise RuntimeError("no inline image in response")
    except Exception as e: return ImageGenResult(False,error=f"Gemini REST image generation failed: {e}",duration_ms=(time.time()-t)*1000)

def _gradio(req, output_path):
    t=time.time()
    try:
        from gradio_client import Client
        space=os.environ.get("QQ_GRADIO_IMAGE_SPACE","black-forest-labs/FLUX.1-schnell")
        client=Client(space)
        w,h=_dims(req)
        result=client.predict(prompt=req.prompt,seed=max(0,req.seed),width=w,height=h,api_name="/infer")
        candidate=result[0] if isinstance(result,(list,tuple)) else result
        if isinstance(candidate,dict): candidate=candidate.get("path") or candidate.get("url")
        if not candidate: raise RuntimeError("Gradio Space returned no image path")
        if str(candidate).startswith(("http://","https://")): data=urllib.request.urlopen(candidate,timeout=180).read()
        else: data=open(str(candidate),"rb").read()
        res=_save(data,output_path); res.model_used=req.model if req.model!="auto" else "FLUX.1-schnell"; res.duration_ms=(time.time()-t)*1000; res.metadata={"route":"gradio","space":space}; return res
    except Exception as e: return ImageGenResult(False,error=f"Gradio image generation failed: {e}",duration_ms=(time.time()-t)*1000)

def generate_image(prompt: str, *, model="auto", aspect_ratio="1:1", resolution="1K",
                   width=0,height=0,quality="",format="png",cfg_scale=7.5,steps=20,seed=0,
                   safe_mode=False,hide_watermark=False,negative_prompt="",style="",
                   output_path="generated.png", method=None, provider=None, **kwargs):
    req=ImageGenRequest(prompt,model,aspect_ratio,resolution,width,height,quality,format,cfg_scale,steps,seed,
                        safe_mode,hide_watermark,False,negative_prompt,style)
    method=method or os.environ.get("QQ_IMAGE_METHOD")
    if not method:
        try:
            cfg=resolve_config(provider=provider or os.environ.get("QQ_PROVIDER"))
            method=cfg.image_backend.provider
            if method=="auto":
                method={"codex":"openai","openai":"openai","gemini":"gemini","gemini-cli":"gemini"}.get(cfg.provider,"gradio")
        except Exception: method="gradio"
    method={"openai_codex":"openai","google":"gemini","gradio_client":"gradio"}.get(method,method)
    if method in ("openai","codex"): return _openai(req,output_path)
    if method=="gemini": return _gemini(req,output_path)
    if method in ("gradio","none","auto"): return _gradio(req,output_path)
    return ImageGenResult(False,error=f"Unknown image generation method: {method}")
