"""채널별 최신 영상의 댓글 초안을 drafts/에 미리 만든다 (게시하지 않음). 이미 있는 초안은 건너뛴다.

사용: uv run python src/make_drafts.py [채널당 영상 수, 기본 15 = RSS 전체]
"""
import sys
import time
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv

import drafter
import drafts
import youtube

ROOT = Path(__file__).resolve().parent.parent


def main():
    per_channel = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    load_dotenv(ROOT / ".env")
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    client = anthropic.Anthropic()

    total = 0.0
    for channel_id in config["channels"]:
        for video in youtube.latest_videos(channel_id)[:per_channel]:
            if drafts.load(video["video_id"]):
                continue
            started = time.time()
            record = drafts.create(client, video, config["comment"])
            cost = drafter.cost_usd(record["usage"])
            total += cost
            basis = record["basis"]
            print(f"\n[{video['channel']}] {video['title']}  ({video['video_id']})")
            print(f"  자막 {basis['transcript_chars']:,}자({basis['transcript_status']}) · 장면 이미지 {basis['scene_images']}장 · 인기 댓글 {basis['top_comments']}개 · {time.time() - started:.0f}초 · ${cost:.3f} · 시도 {record['attempts']}회")
            for key in ("worry", "hook", "comment"):
                if key in record:
                    print(f"  {key:8s} {record[key]}")
            print(f"  검사     {'통과' if not record['problems'] else ' / '.join(record['problems'])}")
    print(f"\n합계 비용: ${total:.3f}")


if __name__ == "__main__":
    main()
