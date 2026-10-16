"""크롬 프로필로 영상 페이지를 열어 댓글을 한 글자씩 입력 · 게시하고, 내 댓글이 보이는지 확인한다.

- 프로필 폴더를 지정해 연다(launch_persistent_context). 쿠키 · 비밀번호 파일은 읽지 않는다 — 로그인 상태는 Chrome이 스스로 쓴다.
- 여는 페이지는 게시 대상 영상 하나뿐이고, 댓글 입력 · 게시 외의 동작(구독 · 좋아요 · 설정 변경)은 하지 않는다.
- 선택자 근거: docs/spike-01-게시-흐름.md
"""
from datetime import datetime

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

TYPING_DELAY_MS = 80


class PostError(Exception):
    def __init__(self, reason, screenshot=None):
        super().__init__(reason)
        self.reason = reason
        self.screenshot = screenshot


def post_comment(profile_dir, video_id, text, shot_dir, on_status):
    """게시 결과 {"comment_url", "screenshot"}. 실패하면 PostError(사유, 캡처 파일명)."""
    on_status("opening", "크롬 프로필 여는 중")
    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                str(profile_dir),
                channel="chrome",
                headless=False,
                # Playwright 기본값인 가짜 키체인을 쓰면 Chrome이 자기 로그인 쿠키를 복호화하지 못한다
                ignore_default_args=["--use-mock-keychain"],
                viewport={"width": 1280, "height": 860},
            )
        except PlaywrightError as e:
            raise PostError(f"크롬 프로필을 열지 못했습니다. 같은 프로필 창이 열려 있다면 닫아 주세요 ({e.message.splitlines()[0]})")
        page = context.pages[0] if context.pages else context.new_page()
        try:
            return _post(page, video_id, text, shot_dir, on_status)
        except PostError as e:
            e.screenshot = _screenshot(page, shot_dir, video_id, "failed")
            raise
        except PlaywrightError as e:
            raise PostError(f"브라우저 작업 실패: {e.message.splitlines()[0]}", _screenshot(page, shot_dir, video_id, "failed"))
        finally:
            context.close()


def _post(page, video_id, text, shot_dir, on_status):
    page.goto(f"https://www.youtube.com/watch?v={video_id}", wait_until="domcontentloaded")
    page.wait_for_selector('#avatar-btn, a[href*="accounts.google.com/ServiceLogin"]', timeout=20000)
    if not page.locator("#avatar-btn").count():
        raise PostError("이 크롬 프로필은 유튜브에 로그인되어 있지 않습니다")

    # 댓글 영역은 스크롤해야 로드된다
    placeholder = page.locator("ytd-comment-simplebox-renderer #simplebox-placeholder").first
    for _ in range(15):
        if placeholder.is_visible():
            break
        page.mouse.wheel(0, 600)
        page.wait_for_timeout(700)
    if not placeholder.is_visible():
        raise PostError("댓글 창을 찾지 못했습니다 (댓글이 꺼졌거나 비공개인 영상일 수 있습니다)")

    placeholder.scroll_into_view_if_needed()
    placeholder.click()
    box = page.locator("ytd-comment-simplebox-renderer #contenteditable-root").first
    box.wait_for(state="visible", timeout=10000)
    on_status("typing", "댓글 입력 중")
    box.press_sequentially(text, delay=TYPING_DELAY_MS)
    # 같은 ID의 숨은 버튼이 여럿 있어 댓글 상자(ytd-commentbox) 안으로 범위를 좁힌다
    page.locator("ytd-commentbox #submit-button button").click()

    on_status("typing", "게시 후 내 댓글 확인 중")
    mine = page.locator("#comments #contents").get_by_text(text).first
    try:
        mine.wait_for(timeout=20000)
    except PlaywrightTimeoutError:
        raise PostError("게시 후 내 댓글이 목록에 보이지 않습니다 (검토 대기로 빠졌을 수 있습니다)")
    mine.scroll_into_view_if_needed()

    # 댓글 시각 링크(…&lc=댓글ID)가 있으면 그 댓글로 바로 가는 주소를 쓴다
    link = page.locator("ytd-comment-thread-renderer").filter(has_text=text).locator("#published-time-text a").first
    href = link.get_attribute("href") if link.count() else None
    comment_url = f"https://www.youtube.com{href}" if href and href.startswith("/") else f"https://www.youtube.com/watch?v={video_id}"

    screenshot = _screenshot(page, shot_dir, video_id, "posted")
    page.wait_for_timeout(5000)  # 게시된 내 댓글을 화면에서 확인할 수 있도록 잠시 둔다
    return {"comment_url": comment_url, "screenshot": screenshot}


def _screenshot(page, shot_dir, video_id, tag):
    shot_dir.mkdir(parents=True, exist_ok=True)
    path = shot_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{video_id}-{tag}.png"
    try:
        page.screenshot(path=str(path))
    except PlaywrightError:
        return None
    return path.name
