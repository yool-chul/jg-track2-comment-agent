import youtube

BASE = "https://i.ytimg.com/sb/VID/storyboard3_L$L/$N.jpg?sqp=abc"


def spec(count):
    return f"{BASE}|48#27#100#10#10#0#default#rs$AAA|80#45#{count}#10#10#1000#M$M#rs$BBB|160#90#{count}#5#5#1000#M$M#rs$CCC"


def test_storyboard_urls_use_largest_level_and_every_sheet_of_short_video():
    # 91장면 · 시트당 25장면 → 시트 4장 전부
    assert youtube.storyboard_urls(spec(91)) == [
        f"https://i.ytimg.com/sb/VID/storyboard3_L2/M{n}.jpg?sqp=abc&sigh=rs$CCC" for n in range(4)
    ]


def test_storyboard_urls_sample_evenly_across_long_video():
    # 1000장면 → 시트 40장 중 처음 · 끝을 포함해 고르게 6장
    urls = youtube.storyboard_urls(spec(1000))
    assert [u.split("/")[-1].split(".")[0] for u in urls] == ["M0", "M8", "M16", "M23", "M31", "M39"]


def test_parse_video_id():
    assert youtube.parse_video_id("https://youtu.be/KRRIF15e3hk") == "KRRIF15e3hk"
    assert youtube.parse_video_id("https://www.youtube.com/watch?v=hpEnIwoH_sw&t=10s") == "hpEnIwoH_sw"
    assert youtube.parse_video_id("https://example.com/x") is None
