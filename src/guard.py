"""운영 규칙 — 게시 전에 서버가 반드시 거친다: 허용 범위 · 영상당 1개 · 하루 상한 · 댓글 규칙. 기록은 data/history.jsonl."""
import json

import drafter


def load_history(path):
    """게시 기록(오래된 순). 각 줄: time · video_id · title · channel · profile · comment · status(success/failed/blocked)."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_history(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def is_allowed(video, config):
    """우리 채널 5개의 영상이거나, 설정에 등록한 본인 테스트 영상인가."""
    return video["channel_id"] in config["channels"] or video["video_id"] in config.get("test_videos", [])


def posted_count_today(history, today):
    return sum(1 for r in history if r["status"] == "success" and r["time"][:10] == today.isoformat())


def check_post(video, comment, history, config, today):
    """게시를 막아야 할 이유 목록. 비어 있으면 게시해도 된다."""
    problems = []
    if not is_allowed(video, config):
        problems.append("허용된 채널(우리 채널 5개 · 본인 테스트 영상)의 영상이 아닙니다")
    if config.get("test_only") and video["video_id"] not in config.get("test_videos", []):
        problems.append("테스트 모드: 본인 테스트 영상에만 게시할 수 있습니다 (config.yaml의 test_only)")
    if any(r["status"] == "success" and r["video_id"] == video["video_id"] for r in history):
        problems.append("이미 댓글을 단 영상입니다 (영상당 1개)")
    limit = config["limits"]["daily_max_comments"]
    if posted_count_today(history, today) >= limit:
        problems.append(f"오늘 게시 상한({limit}개)에 도달했습니다")
    return problems + drafter.check(comment, config["comment"])
