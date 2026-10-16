"""대시보드 서버 — 127.0.0.1에서만 열린다. 화면(static/)과 영상 불러오기 · 초안 · 게시 · 기록 API.

실행: uv run python src/server.py  → 브라우저에서 http://127.0.0.1:8080 이 열린다 (--no-browser로 끌 수 있음)
"""
import os
import sys
import threading
import uuid
import webbrowser
from datetime import date, datetime
from pathlib import Path

import anthropic
import requests
import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import drafts
import guard
import poster
import youtube

ROOT = Path(__file__).resolve().parent.parent
HOST, PORT = "127.0.0.1", 8080
HISTORY = ROOT / "data" / "history.jsonl"
SHOTS = ROOT / "data" / "screenshots"
STATIC = Path(__file__).resolve().parent / "static"

load_dotenv(ROOT / ".env")
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
SHOTS.mkdir(parents=True, exist_ok=True)

app = FastAPI()


@app.middleware("http")
async def no_cache_screen(request, call_next):
    """화면 파일을 고치면 새로고침만으로 바로 반영되게 브라우저 캐시를 쓰지 않는다."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/screenshots", StaticFiles(directory=SHOTS), name="screenshots")

videos = {}  # 불러온 영상(video_id → 정보). 게시는 여기 있는 영상에만 할 수 있다
jobs = {}  # 게시 작업 진행 상태
post_lock = threading.Lock()  # 한 번에 하나만 게시한다


class LinkIn(BaseModel):
    url: str


class PostIn(BaseModel):
    video_id: str
    comment: str
    profile: str  # 프로필 이름 또는 "auto"(자동 배정)


def ai_key_set():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def profile_dir(name):
    return ROOT / "profiles" / name


def summary(video, history):
    posted = {r["video_id"] for r in history if r["status"] == "success"}
    return {**video, "has_draft": drafts.load(video["video_id"]) is not None, "posted": video["video_id"] in posted}


def history_record(video, profile, comment, status, **extra):
    return {
        "time": datetime.now().isoformat(timespec="seconds"),
        "video_id": video["video_id"],
        "title": video["title"],
        "channel": video["channel"],
        "profile": profile,
        "comment": comment,
        "status": status,
        **extra,
    }


def pick_profile(history):
    """준비된(폴더가 있는) 프로필 중 게시가 가장 적은 것 — 영상마다 돌아가며 배정된다."""
    ready = [n for n in CONFIG["profiles"] if profile_dir(n).exists()]
    posts = {n: sum(1 for r in history if r["status"] == "success" and r["profile"] == n) for n in ready}
    return min(ready, key=posts.get) if ready else None


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    history = guard.load_history(HISTORY)
    return {
        "ai_key": ai_key_set(),  # 키 값은 내보내지 않고 설정 여부만
        "test_only": bool(CONFIG.get("test_only")),
        "today": guard.posted_count_today(history, date.today()),
        "daily_max": CONFIG["limits"]["daily_max_comments"],
        "profiles": [{"name": n, "ready": profile_dir(n).exists()} for n in CONFIG["profiles"]],
    }


@app.get("/api/videos")
def load_videos():
    try:
        found = [v | {"test": False} for channel_id in CONFIG["channels"] for v in youtube.latest_videos(channel_id)]
        found += [v | {"test": True} for v in map(youtube.video_info, CONFIG.get("test_videos", [])) if v]
    except requests.RequestException:
        raise HTTPException(502, "유튜브에서 영상 목록을 가져오지 못했습니다. 인터넷 연결을 확인해 주세요")
    videos.clear()
    videos.update((v["video_id"], v) for v in found)
    history = guard.load_history(HISTORY)
    return sorted((summary(v, history) for v in found), key=lambda v: (v["test"], v["published"]), reverse=True)


@app.post("/api/videos/link")
def add_link(body: LinkIn):
    video_id = youtube.parse_video_id(body.url)
    if not video_id:
        raise HTTPException(400, "유튜브 영상 링크가 아닙니다")
    video = youtube.video_info(video_id)
    if not video:
        raise HTTPException(404, "영상을 찾을 수 없습니다 (비공개 · 삭제된 영상일 수 있습니다)")
    video["test"] = video_id in CONFIG.get("test_videos", [])
    if not guard.is_allowed(video, CONFIG):
        raise HTTPException(403, f"허용되지 않은 채널의 영상입니다 ({video['channel']}). 우리 채널 5개와 본인 테스트 영상만 추가할 수 있습니다")
    videos[video_id] = video
    return summary(video, guard.load_history(HISTORY))


@app.get("/api/videos/{video_id}/draft")
def get_draft(video_id: str, regenerate: bool = False):
    video = videos.get(video_id)
    if not video:
        raise HTTPException(404, "먼저 영상 목록을 불러오세요")
    draft = None if regenerate else drafts.load(video_id)
    if draft:
        return draft
    if not ai_key_set():
        raise HTTPException(404, "이 영상의 초안이 없습니다. .env에 AI 키를 넣으면 바로 만들 수 있어요")
    try:
        return drafts.create(anthropic.Anthropic(), video, CONFIG["comment"])
    except anthropic.APIError as e:
        raise HTTPException(502, f"AI 초안 생성에 실패했습니다 ({type(e).__name__})")


@app.post("/api/post")
def start_post(body: PostIn):
    if not post_lock.acquire(blocking=False):
        raise HTTPException(409, "다른 댓글을 게시하는 중입니다")
    try:
        video = videos.get(body.video_id)
        if not video:
            raise HTTPException(404, "먼저 영상 목록을 불러오세요")
        history = guard.load_history(HISTORY)
        profile = pick_profile(history) if body.profile == "auto" else body.profile
        if profile not in CONFIG["profiles"] or not profile_dir(profile).exists():
            raise HTTPException(400, "사용할 수 있는 크롬 프로필이 없습니다. README의 프로필 연결 방법을 확인해 주세요")
        problems = guard.check_post(video, body.comment, history, CONFIG, date.today())
        if problems:
            guard.append_history(HISTORY, history_record(video, profile, body.comment, "blocked", reason=" / ".join(problems)))
            raise HTTPException(400, {"problems": problems})
    except HTTPException:
        post_lock.release()
        raise
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"state": "queued", "message": "대기 중", "profile": profile}
    threading.Thread(target=run_post, args=(job_id, video, profile, body.comment), daemon=True).start()
    return {"job_id": job_id, "profile": profile}


def run_post(job_id, video, profile, comment):
    def on_status(state, message):
        jobs[job_id].update(state=state, message=message)

    try:
        result = poster.post_comment(profile_dir(profile), video["video_id"], comment, SHOTS, on_status)
        jobs[job_id].update(state="posted", message="게시 완료", **result)
        guard.append_history(HISTORY, history_record(video, profile, comment, "success", **result))
    except poster.PostError as e:
        jobs[job_id].update(state="failed", message=e.reason, screenshot=e.screenshot)
        guard.append_history(HISTORY, history_record(video, profile, comment, "failed", reason=e.reason, screenshot=e.screenshot))
    except Exception as e:  # 예상 못 한 오류에도 작업이 '진행 중'으로 멈춰 있지 않게 한다
        reason = f"알 수 없는 오류 ({type(e).__name__})"
        jobs[job_id].update(state="failed", message=reason)
        guard.append_history(HISTORY, history_record(video, profile, comment, "failed", reason=reason))
    finally:
        post_lock.release()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "게시 작업을 찾을 수 없습니다")
    return jobs[job_id]


@app.get("/api/history")
def history():
    return list(reversed(guard.load_history(HISTORY)))


if __name__ == "__main__":
    if "--no-browser" not in sys.argv:
        threading.Timer(1.5, webbrowser.open, args=[f"http://{HOST}:{PORT}"]).start()
    uvicorn.run(app, host=HOST, port=PORT)
