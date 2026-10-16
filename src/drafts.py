"""초안 저장소: drafts/<video_id>.json 읽기 · 만들기. AI 키가 없는 PC에서는 미리 만들어 둔 이 초안을 쓴다."""
import json
from datetime import datetime
from pathlib import Path

import drafter
import youtube

DRAFTS_DIR = Path(__file__).resolve().parent.parent / "drafts"


def load(video_id):
    path = DRAFTS_DIR / f"{video_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def recent_comments(limit=20):
    """최근에 만든 초안의 댓글들 — 새 초안이 표현을 겹치지 않게 하려고 넘긴다."""
    paths = sorted(DRAFTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)[-limit:]
    comments = (json.loads(p.read_text(encoding="utf-8")).get("comment") for p in paths)
    return [c for c in comments if c]


def create(client, video, rules):
    """자막 · 인기 댓글(자막이 없으면 장면 미리보기)을 모아 초안을 만들고 저장한다."""
    transcript_text, transcript_status = youtube.transcript(video["video_id"])
    frames = [] if transcript_text else youtube.storyboard_sheets(video["video_id"])
    # 우리가 단 댓글(운명원 언급)은 인기 댓글 참고에서 뺀다 — 이전 초안을 따라 쓰지 않게
    comments = [c for c in youtube.top_comments(video["video_id"]) if rules["brand"] not in c["text"]]
    result = drafter.draft(client, video, transcript_text, comments, rules, avoid=recent_comments(), frames=frames)
    record = {
        "video_id": video["video_id"],
        "channel": video["channel"],
        "title": video["title"],
        **result,
        "basis": {
            "transcript_chars": len(transcript_text or ""),
            "transcript_status": transcript_status,
            "scene_images": len(frames),
            "top_comments": len(comments),
        },
        "model": drafter.MODEL,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    DRAFTS_DIR.mkdir(exist_ok=True)
    path = DRAFTS_DIR / f"{video['video_id']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record
