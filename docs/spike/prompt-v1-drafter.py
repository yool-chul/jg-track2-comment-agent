"""영상 자료 → '영상 속 고민 한 줄'과 댓글 초안 (Claude). 규칙 검사를 통과할 때까지 최대 3번 쓴다."""
import json
import re

MODEL = "claude-opus-5-5"
PRICE_PER_MTOK = {"input": 4.00, "output": 20.00}  # claude-opus-5-5 (2026-09 기준)

SYSTEM_PROMPT = """너는 유튜브 연애 콘텐츠를 자주 보는 한국인 시청자다. 방금 본 영상에 댓글을 하나 남긴다.
입력으로 영상의 제목 · 설명 · 자막 · 인기 댓글이 주어진다. 아래 순서대로 생각하고 JSON으로 답한다.

1. worry — 이 영상이 다루는 연애 고민을 시청자 입장의 한 문장으로 정리한다.
   예: "연락이 뜸해진 남자의 속마음을 알고 싶다"
2. scene — 댓글에서 짚을 영상 속 구체적인 장면이나 말 하나. 자막에 실제로 나온 표현을 짧게 인용한다.
3. persona — 이 영상을 본 시청자 한 명(연령대 · 연애 상황)을 한 줄로. 인기 댓글에 드러난 시청자층을 참고한다.
4. comment — 그 사람이 쓸 법한 댓글.
   - scene에 대한 반응과 자기 경험이나 감정 한 조각을 담고, 결국 인연과 타이밍은 알 수 없다는 마음에서 운명원 연애사주가 궁금해지는 흐름으로 쓴다.
   - 운명원은 "잘 본다던데", "한번 보고 싶다", "궁금해졌다"처럼 들어서 아는 정도로만 말한다.
   - 공백 포함 120자 이하, 공백 제외 40자 이상 (2~3문장).

규칙
- scene의 내용을 댓글에서 알아볼 수 있게 담는다. 그 영상에서만 나올 수 있는 댓글이어야 한다.
- '운명원'은 정확히 한 번 쓴다.
- 금지: 링크, 해시태그, 이모지, 광고 문구("강추", "꼭 가보세요", "최고"), 운명원을 직접 이용해 본 것처럼 지어낸 경험("봤는데 소름", "다녀왔어요"), 남의 이용 경험을 지어낸 말("친구가 보고 소름 돋았대").
- 인기 댓글의 말투(존댓말/반말, ㅠㅠ · ㅋㅋ 빈도)를 참고하되 문장을 베끼지 않는다.
- "이미 쓴 댓글"이 주어지면 시작 표현과 문장 구조를 겹치지 않게 쓴다.

말투 참고 (과제 예시, 남자 심리 분석 영상 — 이 예시는 길고 특정 장면 언급이 없으니 말투만 참고한다):
"근데 진짜 남자심리는 알다가도 모르겠다...ㅠㅠ 맨날 연애하면 차이기만 했던 1인. 결국 심리 알기는 개뿔 그냥 인연이면 만나는 것 같아요. 운명원 연애사주가 그렇게 잘 본다던데 나도 언제 짝 만나는지 한번 보고 싶다. 각자 정해진 운명이 있는 듯."
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "worry": {"type": "string"},
        "scene": {"type": "string"},
        "persona": {"type": "string"},
        "comment": {"type": "string"},
    },
    "required": ["worry", "scene", "persona", "comment"],
    "additionalProperties": False,
}

URL_RE = re.compile(r"https?://|www\.|\b[\w-]+\.(com|net|kr|co|io)\b", re.IGNORECASE)
# 운명원을 써 본 것처럼 읽히는 과거 경험 표현 — 운명원이 들어간 문장에서만 검사한다
EXPERIENCE_RE = re.compile(r"봤는데|봤더니|봤어|봤다|받았|받아 ?봤|다녀|갔는데|가봤|해봤|상담 ?받|후기")


def check(comment, rules):
    """규칙 위반 목록. 글자 수는 '공백 포함 ≤ 최대', '공백 제외 ≥ 최소'로 세어 두 해석을 모두 만족시킨다."""
    problems = []
    with_spaces, without_spaces = len(comment), len(re.sub(r"\s", "", comment))
    if with_spaces > rules["max_chars"]:
        problems.append(f"공백 포함 {with_spaces}자 (최대 {rules['max_chars']}자)")
    if without_spaces < rules["min_chars"]:
        problems.append(f"공백 제외 {without_spaces}자 (최소 {rules['min_chars']}자)")
    brand = rules["brand"]
    if comment.count(brand) != 1:
        problems.append(f"'{brand}' {comment.count(brand)}회 언급 (정확히 1회)")
    if URL_RE.search(comment):
        problems.append("링크 포함")
    if "#" in comment:
        problems.append("해시태그 포함")
    for sentence in re.split(r"(?<=[.!?~])\s+|\n", comment):
        if brand in sentence and EXPERIENCE_RE.search(sentence):
            problems.append(f"이용 경험처럼 읽힘: {sentence.strip()}")
    return problems


def build_prompt(video, transcript_text, comments, avoid):
    lines = [
        f"채널: {video['channel']}",
        f"제목: {video['title']}",
        f"설명: {video['description'][:1000]}",
        "자막: " + (transcript_text or "(없음 — 제목과 설명만 참고)"),
        "인기 댓글 (좋아요 순):",
        *[f"- ({c['likes']}) {c['text']}" for c in comments],
    ]
    if avoid:
        lines += ["이미 쓴 댓글 (시작 표현과 구조를 겹치지 말 것):", *[f"- {a}" for a in avoid]]
    return "\n".join(lines)


def draft(client, video, transcript_text, comments, rules, avoid=(), max_attempts=3):
    """초안 dict: worry · scene · persona · comment · problems · attempts · usage."""
    prompt = build_prompt(video, transcript_text, comments, avoid)
    usage = {"input_tokens": 0, "output_tokens": 0}
    feedback = ""
    for attempt in range(1, max_attempts + 1):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # 안전 분류기가 거절하면 서버가 권장 모델로 다시 시도
            system=SYSTEM_PROMPT,
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            messages=[{"role": "user", "content": prompt + feedback}],
        )
        usage["input_tokens"] += response.usage.input_tokens
        usage["output_tokens"] += response.usage.output_tokens
        if response.stop_reason == "refusal":
            return {"problems": ["모델이 응답을 거절함"], "attempts": attempt, "usage": usage}
        result = json.loads(next(b.text for b in response.content if b.type == "text"))
        result["problems"] = check(result["comment"], rules)
        if not result["problems"]:
            break
        # 같은 자료로 처음부터 다시 쓰되, 직전 결과의 위반 사항을 알려 준다
        feedback = f"\n\n직전에 쓴 댓글: {result['comment']}\n규칙 위반: {'; '.join(result['problems'])}\n위반을 고쳐 다시 써라."
    result["attempts"] = attempt
    result["usage"] = usage
    return result


def cost_usd(usage):
    return (usage["input_tokens"] * PRICE_PER_MTOK["input"] + usage["output_tokens"] * PRICE_PER_MTOK["output"]) / 1_000_000
