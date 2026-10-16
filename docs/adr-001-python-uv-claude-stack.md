---
aliases: [ADR-001, 기술 스택 ADR]
created: 2026-10-15
tags: [project/jg-group-test, topic/architecture, topic/adr, tool/python, tool/playwright]
type: adr
status: active
related_projects: [jg-group-test]
---

# ADR-001: Python + uv · FastAPI · Playwright · Claude 단일 스택 채택

## 배경

- 심사자 Mac에서 README만 보고 **10분 안에** localhost 대시보드를 띄워야 한다
- 키 없이 RSS · 자막 · 인기 댓글을 수집해야 한다. 자막은 "영상 속 구체적인 장면 · 말"(맥락 이해 25점)의 재료다
- 심사자 PC에는 AI 키가 없다 → `drafts/` 사전 생성이 필수, 키가 있으면 즉석 생성(가점)
- 안전 규칙: 유튜브와 AI 서비스 외 외부 전송 금지 → 텔레메트리 · 외부 CDN을 쓰는 도구는 배제
- 크롬 프로필은 폴더 지정 방식(`launchPersistentContext`, `--user-data-dir`)으로 연결

## 결정

| 영역 | 선택 |
|---|---|
| 런타임 · 패키지 | Python 3.12 + uv (`pyproject.toml` + `uv.lock`, `uv run`으로 실행) |
| 서버 | FastAPI + uvicorn, `127.0.0.1`에만 바인딩 |
| 화면 | 정적 HTML + 바닐라 JS/CSS (빌드 없음, 외부 CDN 없음) |
| 영상 목록 | `requests` + `xml.etree`로 채널 RSS 파싱 (requests는 자막 · 댓글 라이브러리가 이미 의존. 표준 `urllib`은 python.org 배포판에서 인증서 오류 — [[spike-01-게시-흐름]]) |
| 자막 · 인기 댓글 | `youtube-transcript-api`, `youtube-comment-downloader` |
| 게시 자동화 | Playwright for Python — `launch_persistent_context(user_data_dir, channel="chrome", headless=False)` |
| AI | Anthropic Python SDK, 기본 모델 `claude-opus-5-5`, 키는 `.env`의 `ANTHROPIC_API_KEY` |
| 저장 | `config.yaml`, `drafts/*.json`, `data/history.jsonl`, `data/screenshots/` |
| 테스트 | pytest — 운영 가드(허용 채널 · 영상당 1개 · 하루 상한) 단위 테스트 |

## 근거

**스파이크 결과** (2026-10-15, 개발자 Mac, 대상: `hpEnIwoH_sw` · `akn-AvCeHBI`)

| 항목 | Python | Node.js |
|---|---|---|
| RSS | ✅ 채널당 15개, 설명 · 조회수 · 썸네일 포함 | ✅ |
| 자막 (한국어 자동 자막) | ✅ `youtube-transcript-api` 1.2.4 — 666 / 736 구간 | ❌ `youtubei.js` 18.1.0 — 두 영상 모두 HTTP 400 |
| 인기 댓글 + 좋아요 수 | ✅ `youtube-comment-downloader` 0.1.84 | ✅ `youtubei.js` |

- **단일 런타임 · 단일 코드 경로**: 제출 전 초안 일괄 생성과 심사자 PC의 즉석 생성이 같은 코드 → 품질 일치
- **uv**: 심사자 PC에 Python이 없어도 `uv run`이 지정 버전 Python과 의존성을 자동 설치 → 10분 설치 목표에 유리
- **`channel="chrome"`**: 이미 설치된 Chrome 사용 → 별도 브라우저 다운로드 불필요
- **바닐라 HTML/JS**: 빌드 단계가 없어 설치가 짧고 심사자가 코드를 검사하기 쉬움. Streamlit · Gradio는 기본 설정으로 사용 통계를 외부로 보내므로 배제
- **Claude 단일**: 구현 · 검증이 단순. 기본 모델은 품질 우선으로 Opus 5.5 (맥락 이해 · 자연스러움이 핵심 배점)

## 트레이드오프

- 개발자는 Node(Express · Puppeteer)에 더 익숙 → Python 학습 비용
- 심사자가 uv를 먼저 설치해야 함 (`brew install uv` 또는 공식 설치 스크립트) → README에 `python3 -m venv` + `pip` 대안 병기
- 비공식 스크래핑 라이브러리 의존 → 유튜브 변경 시 자막 · 댓글 수집이 깨질 수 있음. 필수 경로는 `drafts/`로 보호하고, 자막 실패 시 제목 · 설명으로 대체(원문이 허용)
- Claude 단일 → 심사자가 다른 회사 키만 있으면 즉석 생성(가점)을 직접 시험할 수 없음. 시연 영상에서 즉석 생성 장면을 보여 보완
- Opus 5.5 비용: 초안 75개 1회 생성에 약 $10 안팎으로 추정(자막 길이에 따라 다름). 필요하면 Sonnet 5.5로 낮출 수 있음

## 참고

- [[00-과제-분석]] — 요구사항 · 배점 · 열린 질문
- [시스템 구성도](diagrams/system-architecture.html)
- 스파이크 코드는 임시 폴더에서만 실행 (저장소 미포함)
