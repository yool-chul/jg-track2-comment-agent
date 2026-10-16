"""게시 흐름 스파이크: 프로필 폴더로 Chrome 열기 → 댓글창 → 한 글자씩 타이핑 → (--post면) 게시 → 내 댓글 확인.

사용: uv run --no-project --with playwright python spike_post.py <프로필 폴더> [--post]
--post가 없으면 타이핑까지만 하고 지운다 (드라이런).
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

VIDEO_URL = "https://www.youtube.com/watch?v=KRRIF15e3hk"
TEXT = "[테스트] 자동 타이핑 게시 확인용 댓글입니다. 곧 삭제할게요."
SHOTS = Path(__file__).parent / "shots"


def shot(page, name):
    path = SHOTS / f"{name}.png"
    page.screenshot(path=str(path))
    print("screenshot:", path)


def run(page, post):
    page.goto(VIDEO_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    avatar = page.locator("#avatar-btn").count()
    sign_in = page.locator('a[href*="accounts.google.com/ServiceLogin"]').count()
    print(f"avatar-btn: {avatar}, sign-in links: {sign_in}")
    if not avatar:
        shot(page, "0-not-signed-in")
        return

    # 댓글 영역은 스크롤해야 로드된다
    placeholder = page.locator("ytd-comment-simplebox-renderer #simplebox-placeholder")
    for _ in range(15):
        if placeholder.count() and placeholder.first.is_visible():
            break
        page.mouse.wheel(0, 600)
        page.wait_for_timeout(700)
    if not (placeholder.count() and placeholder.first.is_visible()):
        ids = page.eval_on_selector_all("#comments [id]", "els => [...new Set(els.map(e => e.id))].slice(0, 40)")
        print("comment box not found; ids under #comments:", ids)
        shot(page, "1-no-comment-box")
        return

    placeholder.first.scroll_into_view_if_needed()
    placeholder.first.click()
    box = page.locator("ytd-comment-simplebox-renderer #contenteditable-root")
    box.first.wait_for(state="visible", timeout=10000)
    box.first.press_sequentially(TEXT, delay=80)
    shot(page, "2-typed")

    if not post:
        page.keyboard.press("Meta+A")
        page.keyboard.press("Backspace")
        page.locator("ytd-commentbox #cancel-button button").click()
        print("dry run: typed and cleared")
        return

    page.locator("ytd-commentbox #submit-button button").click()
    mine = page.locator("#comments #contents").get_by_text(TEXT).first
    mine.wait_for(timeout=20000)
    mine.scroll_into_view_if_needed()
    shot(page, "3-posted")
    print("posted and visible")


def main():
    profile = Path(sys.argv[1]).resolve()
    post = "--post" in sys.argv
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(profile),
            channel="chrome",
            headless=False,
            # Playwright 기본값인 가짜 키체인을 쓰면 Chrome이 자기 로그인 쿠키를 복호화하지 못한다.
            ignore_default_args=["--use-mock-keychain"],
            viewport={"width": 1280, "height": 860},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            run(page, post)
        finally:
            ctx.close()


if __name__ == "__main__":
    main()
