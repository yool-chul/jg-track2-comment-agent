"""유튜브 공개 데이터 수집: 채널 RSS(최신 영상), 영상 정보, 자막, 장면 미리보기, 인기 댓글. API 키를 쓰지 않는다."""
import json
import math
import re
import xml.etree.ElementTree as ET
from itertools import islice
from pathlib import Path

import requests
from youtube_comment_downloader import SORT_BY_POPULAR, YoutubeCommentDownloader
from youtube_transcript_api import CouldNotRetrieveTranscript, IpBlocked, RequestBlocked, YouTubeTranscriptApi

RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})")
PLAYER_RESPONSE = "ytInitialPlayerResponse = "
# 받은 자막은 저장해 두고 다시 요청하지 않는다 — 같은 영상을 반복 요청하면 유튜브가 자막 요청을 일시 차단한다
TRANSCRIPT_CACHE = Path(__file__).resolve().parent.parent / "data" / "transcripts"
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def latest_videos(channel_id):
    """채널의 최신 영상(최대 15개)을 최신순으로 돌려준다."""
    resp = requests.get(RSS_URL.format(channel_id), timeout=15)
    resp.raise_for_status()
    videos = []
    for entry in ET.fromstring(resp.content).findall("a:entry", NS):
        group = entry.find("media:group", NS)
        stats = group.find("media:community/media:statistics", NS)
        videos.append({
            "video_id": entry.findtext("yt:videoId", namespaces=NS),
            "channel_id": channel_id,
            "channel": entry.findtext("a:author/a:name", namespaces=NS),
            "title": entry.findtext("a:title", namespaces=NS),
            "published": entry.findtext("a:published", namespaces=NS),
            "description": group.findtext("media:description", default="", namespaces=NS),
            "thumbnail": group.find("media:thumbnail", NS).get("url"),
            "views": int(stats.get("views")) if stats is not None else None,
        })
    return videos


def parse_video_id(text):
    """유튜브 링크(또는 영상 ID)에서 11자리 영상 ID를 꺼낸다. 아니면 None."""
    text = text.strip()
    if re.fullmatch(r"[\w-]{11}", text):
        return text
    match = VIDEO_ID_RE.search(text)
    return match.group(1) if match else None


def _player_response(video_id):
    """영상 페이지에 실린 공개 플레이어 정보(JSON). 찾지 못하면 None."""
    resp = requests.get(
        f"https://www.youtube.com/watch?v={video_id}",
        headers={"Accept-Language": "ko-KR", "User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    resp.raise_for_status()
    start = resp.text.find(PLAYER_RESPONSE)
    if start < 0:
        return None
    data, _ = json.JSONDecoder().raw_decode(resp.text, start + len(PLAYER_RESPONSE))
    return data


def video_info(video_id):
    """영상 페이지의 공개 메타데이터(채널 확인용). 비공개 · 삭제 영상이면 None."""
    data = _player_response(video_id)
    if not data or data.get("playabilityStatus", {}).get("status") != "OK":
        return None
    details = data["videoDetails"]
    micro = data.get("microformat", {}).get("playerMicroformatRenderer", {})
    return {
        "video_id": video_id,
        "channel_id": details["channelId"],
        "channel": details.get("author", ""),
        "title": details.get("title", ""),
        "published": micro.get("publishDate", ""),
        "description": details.get("shortDescription", ""),
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "views": int(details["viewCount"]) if details.get("viewCount", "").isdigit() else None,
    }


def storyboard_urls(spec, max_sheets=6):
    """스토리보드 스펙 → 가장 큰 장면 시트의 URL들. 시트가 많으면 영상 전체에서 고르게 max_sheets장을 고른다.

    스펙 형식: '기본URL|레벨0|레벨1|…', 레벨 = '가로#세로#장면수#열#행#간격ms#이름#서명'
    """
    base, *levels = spec.split("|")
    level = len(levels) - 1
    _width, _height, count, cols, rows, _interval, name, sigh = levels[level].split("#")[:8]
    sheets = math.ceil(int(count) / (int(cols) * int(rows)))
    if sheets <= max_sheets:
        picks = range(sheets)
    else:
        picks = sorted({round(i * (sheets - 1) / (max_sheets - 1)) for i in range(max_sheets)})
    return [base.replace("$L", str(level)).replace("$N", name.replace("$M", str(n))) + f"&sigh={sigh}" for n in picks]


def storyboard_sheets(video_id, max_sheets=6):
    """자막이 없을 때 쓰는 장면 미리보기 시트(JPEG). 한 장에 여러 장면이 시간순으로 들어 있다. 없으면 []."""
    data = _player_response(video_id)
    spec = (data or {}).get("storyboards", {}).get("playerStoryboardSpecRenderer", {}).get("spec")
    if not spec:
        return []
    sheets = (requests.get(url, timeout=15) for url in storyboard_urls(spec, max_sheets))
    return [r.content for r in sheets if r.ok]


def transcript(video_id):
    """(한국어 자막 전문, 상태). 상태: ok · none(자막 없음) · blocked(유튜브가 자막 요청을 일시 차단).

    자막을 못 가져오면 본문은 None — 원문대로 제목 · 설명(이 프로젝트에선 장면 미리보기도)으로 대체한다.
    """
    cached = TRANSCRIPT_CACHE / f"{video_id}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8"), "ok"
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["ko"])
    except (IpBlocked, RequestBlocked):
        return None, "blocked"
    except CouldNotRetrieveTranscript:
        return None, "none"
    text = " ".join(snippet.text for snippet in fetched)
    TRANSCRIPT_CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8")
    return text, "ok"


def top_comments(video_id, limit=15):
    """인기순 상위 댓글(답글 제외)의 본문과 좋아요 수."""
    comments = YoutubeCommentDownloader().get_comments_from_url(
        f"https://www.youtube.com/watch?v={video_id}", sort_by=SORT_BY_POPULAR
    )
    top_level = (c for c in comments if not c.get("reply"))
    return [{"text": c["text"], "likes": c.get("votes", "0")} for c in islice(top_level, limit)]
