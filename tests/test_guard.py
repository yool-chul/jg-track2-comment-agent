from datetime import date

import guard

CONFIG = {
    "channels": {"UC_OUR_CHANNEL": "우리 채널"},
    "test_videos": ["TESTVIDEO01"],
    "comment": {"min_chars": 40, "max_chars": 120, "brand": "운명원"},
    "limits": {"daily_max_comments": 10},
}
GOOD = "고생했네 한마디로 끝냈던 게 딱 저였어요ㅠ 운명원 연애사주에서는 저랑 남친이 오래 맞춰갈 사이로 나오는지 궁금해요."
TODAY = date(2026, 10, 16)


def video(video_id="VIDEO000001", channel_id="UC_OUR_CHANNEL"):
    return {"video_id": video_id, "channel_id": channel_id}


def record(video_id, status="success", day="2026-10-16"):
    return {"time": f"{day}T10:00:00", "video_id": video_id, "status": status}


def test_our_channel_video_passes():
    assert guard.check_post(video(), GOOD, [], CONFIG, TODAY) == []


def test_other_channel_video_blocked():
    problems = guard.check_post(video(channel_id="UC_SOMEONE_ELSE"), GOOD, [], CONFIG, TODAY)
    assert any("허용된 채널" in p for p in problems)


def test_registered_test_video_allowed():
    assert guard.check_post(video("TESTVIDEO01", "UC_MY_CHANNEL"), GOOD, [], CONFIG, TODAY) == []


def test_second_comment_on_same_video_blocked():
    problems = guard.check_post(video(), GOOD, [record("VIDEO000001")], CONFIG, TODAY)
    assert any("영상당 1개" in p for p in problems)


def test_failed_or_blocked_attempt_does_not_count_as_posted():
    history = [record("VIDEO000001", "failed"), record("VIDEO000001", "blocked")]
    assert guard.check_post(video(), GOOD, history, CONFIG, TODAY) == []


def test_daily_limit_reached():
    history = [record(f"OTHER{i:06d}") for i in range(10)]
    problems = guard.check_post(video(), GOOD, history, CONFIG, TODAY)
    assert any("상한" in p for p in problems)


def test_daily_limit_resets_next_day():
    history = [record(f"OTHER{i:06d}", day="2026-10-15") for i in range(10)]
    assert guard.check_post(video(), GOOD, history, CONFIG, TODAY) == []


def test_test_only_mode_blocks_our_channel_video():
    problems = guard.check_post(video(), GOOD, [], CONFIG | {"test_only": True}, TODAY)
    assert any("테스트 모드" in p for p in problems)


def test_test_only_mode_allows_registered_test_video():
    assert guard.check_post(video("TESTVIDEO01", "UC_MY_CHANNEL"), GOOD, [], CONFIG | {"test_only": True}, TODAY) == []


def test_comment_rules_enforced():
    problems = guard.check_post(video(), "운명원 최고 www.example.com #사주", [], CONFIG, TODAY)
    assert any("링크" in p for p in problems)
    assert any("해시태그" in p for p in problems)
    assert any("공백 제외" in p for p in problems)
