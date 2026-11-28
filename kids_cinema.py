"""Cinematic 3D scene art for حكايات جدو (free tooling only).

Style target: Pixar/Disney-style 3D render, lush detailed environment, warm volumetric light,
full-bleed 9:16 vertical framing (no blurred side bars), consistent mascots.

Image provider chain (all free, no paid keys):
  1. Gemini image (if GEMINI_API_KEY is set - already a repo secret)
  2. Hugging Face Space black-forest-labs/FLUX.1-dev (anonymous, no key)  <- best free look
  3. Pollinations (anonymous, currently the 'sana' model - weakest)
  4. Pexels photo (last resort)
"""
import io, os, random, subprocess, time
from PIL import Image, ImageFilter

VW, VH = 720, 1280          # vertical 9:16 output
FOX = "a small round fluffy orange fox cub with big friendly eyes and a blue scarf"
ELE = "a cute round light-blue baby elephant with huge pink-lined ears and a small yellow bow"
STYLE = ("cinematic 3D animated film still, Pixar-Disney style 3D render, ultra detailed, soft volumetric golden sunlight, "
         "shallow depth of field, rich saturated colors, lush detailed environment, kids cartoon, wholesome, "
         "no text, no watermark, full body wide shot, characters facing camera, vertical 9:16 composition")


def scene_prompt(action, cast="both", env="a bright green garden with flowers, a lily pond and butterflies"):
    who = {"both": f"{ELE} and {FOX}", "fox": FOX, "ele": ELE}[cast]
    return f"{who} {action}, {env}. {STYLE}"


def _gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    import base64, requests
    for m in ("gemini-2.5-flash-image", "gemini-2.0-flash-preview-image-generation"):
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                              params={"key": key}, timeout=180,
                              json={"contents": [{"parts": [{"text": prompt}]}],
                                    "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}})
            if r.status_code != 200:
                continue
            for p in r.json()["candidates"][0]["content"]["parts"]:
                d = p.get("inlineData") or p.get("inline_data")
                if d:
                    return Image.open(io.BytesIO(base64.b64decode(d["data"]))).convert("RGB")
        except Exception as e:
            print("[cinema:gemini]", e)
    return None


def _flux_hf(prompt, seed, steps=28):
    """Free anonymous FLUX.1-dev on Hugging Face Spaces (ZeroGPU). ~25s per image."""
    try:
        from gradio_client import Client
        c = Client("black-forest-labs/FLUX.1-dev", verbose=False)
        r = c.predict(prompt=prompt, seed=seed, randomize_seed=False, width=768, height=1344,
                      guidance_scale=3.5, num_inference_steps=steps, api_name="/infer")
        p = r[0] if isinstance(r, (list, tuple)) else r
        if isinstance(p, dict):
            p = p.get("path")
        return Image.open(p).convert("RGB")
    except Exception as e:
        print("[cinema:flux]", str(e)[:160])
        return None


def _pollinations(prompt, seed):
    try:
        import requests
        r = requests.get("https://image.pollinations.ai/prompt/" + requests.utils.quote(prompt[:900]),
                         params={"width": 720, "height": 1280, "nologo": "true", "seed": seed}, timeout=150)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            w, h = im.size
            return im.crop((0, 0, w, int(h * 0.95)))
    except Exception as e:
        print("[cinema:pollinations]", e)
    return None


def cover(img, w=VW, h=VH):
    r = max(w / img.width, h / img.height)
    im = img.resize((int(img.width * r) + 1, int(img.height * r) + 1), Image.LANCZOS)
    l, t = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((l, t, l + w, t + h))


def make_scene(action, path, cast="both", env=None, seed=20260, fallback=None):
    prompt = scene_prompt(action, cast, env) if env else scene_prompt(action, cast)
    img = _gemini(prompt) or _flux_hf(prompt, seed) or _pollinations(prompt, seed)
    if img is None and fallback and os.path.exists(fallback):
        img = Image.open(fallback)
    if img is None:
        img = Image.new("RGB", (VW, VH), (255, 214, 120))
    cover(img).save(path, quality=95)
    return path


def cinematic_clip(img_path, dur, out, idx=0, fps=30):
    """Slow cinematic push-in / pull-out with a gentle drift - reads as real camera movement."""
    frames = max(int(dur * fps), fps)
    z = "0.0009"
    if idx % 2 == 0:
        zp = f"zoompan=z='min(1+{z}*on,1.16)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    else:
        zp = (f"zoompan=z='max(1.16-{z}*on,1.0)':x='iw/2-(iw/zoom/2)+sin(on/60)*6'"
              f":y='ih/2-(ih/zoom/2)-sin(on/90)*5'")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img_path, "-vf",
           f"scale={VW*2}:{VH*2}:flags=lanczos,{zp}:d={frames}:s={VW}x{VH}:fps={fps},format=yuv420p",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-t", f"{dur:.3f}", out]
    subprocess.run(cmd, check=True, capture_output=True)
    return out
