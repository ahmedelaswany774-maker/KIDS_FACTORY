"""Kids story bot: Gemini story + scenes -> edge-tts per scene -> illustrated scenes (Ken Burns) -> YouTube (made for kids) + Short + custom thumbnail."""
import asyncio, json, os, sys, random
import edge_tts
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from kids_story_generator import generate_story
import kids_media as km

VOICE = os.getenv("TTS_VOICE", "ar-EG-SalmaNeural")   # or ar-SA-ZariyahNeural, ar-EG-ShakirNeural
RATE = os.getenv("TTS_RATE", "-10%")                  # slower = better for kids
PRIVACY = os.getenv("PRIVACY_STATUS", "public")       # public / unlisted / private
PUBLISH_HOUR_UTC = os.getenv("PUBLISH_HOUR_UTC", "15")  # scheduled public release hour (15 UTC = 17:00 Cairo, after school); "" = publish immediately
MAKE_SHORT = os.getenv("MAKE_SHORT", "true").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"  # build video, skip upload
OUT = "out"
os.makedirs(OUT, exist_ok=True)


async def _tts_all(scenes):
    paths = []
    for i, s in enumerate(scenes):
        p = f"{OUT}/voice_{i:02d}.mp3"
        for attempt in range(3):
            try:
                await edge_tts.Communicate(s["narration"], VOICE, rate=RATE).save(p)
                break
            except Exception as e:
                print("tts retry", i, e)
                if attempt == 2:
                    raise
                await asyncio.sleep(3)
        paths.append(p)
    return paths


def youtube():
    creds = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"]))
    if not creds.valid:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload(yt, path, title, desc, tags):
    body = {"snippet": {"title": title[:100], "description": desc, "tags": tags, "categoryId": "27",
                        "defaultLanguage": "ar", "defaultAudioLanguage": "ar"},
            # selfDeclaredMadeForKids is the writable field (madeForKids is read-only and derived from it).
            "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": True}}
    if PRIVACY == "public" and PUBLISH_HOUR_UTC.strip():
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        at = now.replace(hour=int(PUBLISH_HOUR_UTC), minute=0, second=0, microsecond=0)
        if at <= now + timedelta(minutes=30):
            at += timedelta(days=1)
        body["status"].update({"privacyStatus": "private", "publishAt": at.strftime("%Y-%m-%dT%H:%M:%SZ")})
        print("scheduled public release at", body["status"]["publishAt"])
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(path, chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]


def main():
    import kids_story_generator as _k
    if not DRY_RUN and _k.uploaded_today() and os.getenv("FORCE_UPLOAD") != "1":
        print("one-upload-per-day guard: already uploaded today (Cairo date), skipping"); return
    d = generate_story()
    title, scenes, character = d["title"], d["scenes"], d.get("character", "a cute friendly cartoon character")
    tags = [t for t in d.get("tags", [])][:12] + ["قصص أطفال", "kids stories"]
    print("Story:", title, "| scenes:", len(scenes))
    import kids_story_generator as ksg
    km.SEED = ksg.MASCOT_SEED if ksg.MODE == "edu" else random.randint(1, 10**6)  # one seed per story keeps the hero looking the same in every scene
    audios = asyncio.run(_tts_all(scenes))
    imgs = []
    VECTOR = ksg.MODE == "edu" and os.getenv("EDU_STYLE", "vector") == "vector"
    if VECTOR:
        import kids_vector as kv
        os.makedirs(OUT, exist_ok=True)
        for i, s in enumerate(scenes):
            imgs.append(kv.vector_scene(i, s.get("on_screen"), s.get("obj"), s.get("count"), f"{OUT}/scene_{i:02d}.jpg"))
        s0 = scenes[0]
        thumb_base = kv.vector_scene(0, s0.get("on_screen"), s0.get("obj"), 1, f"{OUT}/thumb_base.jpg", who="fox", big=True)
        print("vector scenes:", len(imgs))
    else:
        for i, s in enumerate(scenes):
            imgs.append(km.make_image(s.get("image_prompt", title), character, s.get("search"), f"{OUT}/scene_{i:02d}.jpg", fallback=imgs[-1] if imgs else None))
            print("image", i + 1, "/", len(scenes))
        thumb_prompt = "Close-up of its happy smiling animal face with huge sparkly eyes, centered, empty space at the bottom"
        thumb_base = km.make_image(thumb_prompt, character, "cute animals", f"{OUT}/thumb_base.jpg", fallback=imgs[0])
    try:
        thumb = km.make_thumbnail(thumb_base, d.get("thumbnail_text") or title, f"{OUT}/thumb.jpg")
    except Exception as e:
        print("thumbnail render failed:", e); thumb = thumb_base
    dur = km.assemble(imgs, audios, f"{OUT}/story.mp4", (1280, 720), workdir=OUT, animate=True, title=d.get("hook_title") or title, captions=[s.get("on_screen") for s in scenes])
    print("video seconds:", round(dur))
    try:  # preview files committed to the repo so the result can be checked without downloading the video
        import shutil, subprocess
        os.makedirs("preview", exist_ok=True)
        shutil.copy(thumb, "preview/thumb.jpg")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{OUT}/story.mp4", "-vf",
                        "fps=1/30,scale=320:-1,tile=4x4", "-frames:v", "1", "preview/contact.jpg"], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{OUT}/story.mp4", "-vf", "scale=640:-2", "-c:v", "libx264", "-crf", "30",
                        "-preset", "veryfast", "-c:a", "aac", "-b:a", "64k", "preview/story_small.mp4"], check=True)
    except Exception as e:
        print("preview failed:", e)
    if MAKE_SHORT:
        vimgs = []
        for i, p in enumerate(imgs):
            q = f"{OUT}/vscene_{i:02d}.jpg"; km.vertical_still(p, q); vimgs.append(q)
        km.assemble(vimgs, audios, f"{OUT}/short.mp4", (720, 1280), max_dur=55, workdir=OUT)
    if DRY_RUN:
        print("DRY_RUN: skipping upload"); return
    yt = youtube()
    vid = upload(yt, f"{OUT}/story.mp4", title, d["description"] + "\n\nاشترك في القناة لقصص جديدة كل يوم 🌟", tags)
    url = f"https://www.youtube.com/watch?v={vid}"
    print("Uploaded:", url)
    if ksg.MODE == "edu":
        try:
            ksg.record_history(d)
        except Exception as e:
            print("history save failed:", e)
    try:
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumb, mimetype="image/jpeg")).execute()
        print("Thumbnail set")
    except Exception as e:
        print("Thumbnail failed:", e)
    if MAKE_SHORT:
        sid = upload(yt, f"{OUT}/short.mp4", f"{title} #Shorts",
                     f"{d['description']}\n\nالقصة كاملة: {url}\n#Shorts #قصص_أطفال", tags + ["Shorts"])
        print("Short:", f"https://www.youtube.com/shorts/{sid}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAILED:", e); sys.exit(1)
