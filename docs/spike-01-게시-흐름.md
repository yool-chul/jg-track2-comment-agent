---
created: 2026-10-15
tags: [project/jg-group-test, topic/spike, tool/playwright]
status: done
---

# 스파이크 01 — 크롬 프로필로 댓글 게시 흐름 검증

> 결과: ✅ 성공 (2026-10-15) — 본인 테스트 영상(`KRRIF15e3hk`, 일부공개)에 테스트 댓글 1개 게시 · 확인
> 스크립트: [spike_post.py](spike/spike_post.py) · 캡처: [타이핑](spike/01-typed.png) · [게시 확인](spike/02-posted.png)

## 검증한 것

| 단계 | 결과 |
|---|---|
| 프로필 폴더로 Chrome 열기 | ✅ `launch_persistent_context("profiles/유튜브1", channel="chrome", headless=False, ignore_default_args=["--use-mock-keychain"])` |
| 로그인 유지 | ✅ 일반 크롬으로 1회 수동 로그인한 폴더를 Playwright로 다시 열어도 로그인 상태 (아바타 확인). 코드는 쿠키 · 비밀번호에 접근하지 않음 |
| 한국어 화면 | ✅ 한국어 UI에서 동작 |
| 댓글창 → 한 글자씩 타이핑 | ✅ `press_sequentially(text, delay=80)`, 한글 정상 입력 |
| 게시 → 내 댓글 확인 | ✅ 게시 직후 댓글 목록 맨 위에 표시 |

## 선택자 (2026-10 기준, 화면 언어와 무관한 ID 기반)

| 용도 | 선택자 |
|---|---|
| 로그인 확인 | `#avatar-btn` |
| 댓글창 열기 | `ytd-comment-simplebox-renderer #simplebox-placeholder` (스크롤해야 로드됨) |
| 입력 영역 | `ytd-comment-simplebox-renderer #contenteditable-root` |
| 게시 버튼 | `ytd-commentbox #submit-button button` (aria-label "댓글", 입력 전엔 disabled) |
| 취소 버튼 | `ytd-commentbox #cancel-button button` (aria-label "취소") |
| 내 댓글 확인 | `#comments #contents` 안에서 본문 텍스트 일치 |

## 실패와 개선 (PROCESS.md 재료)

1. **비공개 영상엔 댓글 영역이 없다** — 테스트 영상이 비공개라 댓글창을 찾지 못함 → 일부공개로 바꿔 해결. 공개 상태는 영상 페이지의 `playabilityStatus`로 미리 확인할 수 있음
2. **같은 ID를 가진 숨은 버튼** — `#cancel-button`이 3개 매치(첨부 미리보기용 숨은 요소 2개)되어 `.first`가 숨은 요소를 누르다 30초 타임아웃 → `ytd-commentbox` 범위로 좁혀 해결
3. **Python 표준 `urllib`의 HTTPS 인증서 오류** — python.org 배포판 Python에서 `CERTIFICATE_VERIFY_FAILED` → 앱의 HTTP 요청은 `requests`로 처리 ([[adr-001-python-uv-claude-stack]] 갱신)

## 아직 확인하지 않은 것

- `--use-mock-keychain`을 끄지 않으면 로그인이 풀리는지 (끈 상태로만 검증함)
- 영상당 1개 · 하루 상한 · 허용 채널 차단 — 앱 구현 단계에서 pytest로 검증
- 다른 계정 프로필(유튜브2 · 3), 댓글이 검토 대기로 빠지는 경우의 확인 로직
- 테스트 댓글은 영상에 남아 있음 — 수동 삭제 필요
