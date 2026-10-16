// 대시보드 화면 — 메인(① 불러오기 · 검색 · 목록) → 상세(영상 · ② 고민 · 초안 · ③ 댓글 달기, 댓글을 단 영상은 기록만) + 전체 기록.
// 주소: #/ 목록 · #/video/<영상ID> 상세 · #/history 전체 기록
// 유튜브에서 받은 문자열은 모두 textContent로 넣어 HTML로 해석되지 않게 한다.
const $ = (id) => document.getElementById(id);
const BRAND = "운명원";
const LIMITS = { max: 120, min: 40 };
const RESULT = { success: "성공", failed: "실패", blocked: "차단" };
const state = { videos: [], status: null, current: null, posting: false, query: "", filters: { comment: "all", draft: "all", kind: "all" } };

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = body.detail;
    const error = new Error(typeof detail === "string" ? detail : `요청에 실패했습니다 (${res.status})`);
    error.problems = detail?.problems;
    throw error;
  }
  return body;
}

function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

// 버튼 안에 동그란 스피너를 띄우고 비활성화한다. busy=false면 원래 글자로 되돌린다.
function setBusy(button, busy, label = "") {
  button.disabled = busy;
  button.classList.toggle("busy", busy);
  if (busy) {
    button.dataset.label = button.textContent;
    button.replaceChildren(el("span", { className: "spinner" }), label);
  } else {
    button.textContent = button.dataset.label;
  }
}

function setMsg(id, text, kind = "") {
  $(id).textContent = text;
  $(id).className = `msg ${kind}`;
}

const day = (iso) => (iso || "").slice(0, 10);
const when = (iso) => iso.slice(5, 16).replace("T", " ");

function videoBadges(v) {
  const badges = el("div", { className: "badges" });
  if (v.test) badges.append(el("span", { className: "badge test", textContent: "테스트 영상" }));
  badges.append(el("span", { className: v.posted ? "badge posted" : "badge", textContent: v.posted ? "✓ 댓글 달림" : "댓글 없음" }));
  if (v.has_draft) badges.append(el("span", { className: "badge draft", textContent: "초안 있음" }));
  return badges;
}

// ---------- 상태 · 프로필 ----------
async function refreshStatus() {
  const s = await api("/api/status");
  state.status = s;
  $("chip-test").hidden = !s.test_only;
  $("chip-ai").textContent = s.ai_key ? "AI 키 설정됨 · 새 영상 초안 생성 가능" : "AI 키 없음 · 저장된 초안 사용";
  $("chip-ai").classList.toggle("on", s.ai_key);
  $("chip-today").textContent = `오늘 게시 ${s.today}/${s.daily_max}`;

  const select = $("sel-profile");
  const current = select.value;
  select.replaceChildren(el("option", { value: "auto", textContent: "자동 배정 (영상마다 돌아가며)" }));
  for (const p of s.profiles) {
    select.append(el("option", { value: p.name, disabled: !p.ready, textContent: p.ready ? p.name : `${p.name} (설정 안 됨)` }));
  }
  const firstReady = s.profiles.find((p) => p.ready);
  select.value = current || (firstReady ? firstReady.name : "auto");
}

// ---------- 화면 전환 ----------
async function route() {
  const [, page, id] = location.hash.split("/");
  const view = page === "video" && id ? "detail" : page === "history" ? "history" : "list";
  for (const name of ["list", "detail", "history"]) $(`view-${name}`).hidden = name !== view;
  $("nav-list").classList.toggle("active", view !== "history");
  $("nav-history").classList.toggle("active", view === "history");
  window.scrollTo(0, 0);
  if (view !== "detail") {
    state.current = null;
    hideLoading();
  }
  if (view === "detail") await openDetail(decodeURIComponent(id));
  else if (view === "history") await loadHistory();
  else renderList();
}

// ---------- 메인: 불러오기 · 검색 · 목록 ----------
async function loadVideos() {
  setBusy($("btn-load"), true, "불러오는 중…");
  setMsg("load-msg", "우리 채널 5개의 최신 영상을 불러오는 중…");
  try {
    state.videos = await api("/api/videos");
    renderList();
  } catch (e) {
    setMsg("load-msg", e.message, "error");
  } finally {
    setBusy($("btn-load"), false);
  }
}

async function addLink(event) {
  event.preventDefault();
  const url = $("input-link").value.trim();
  if (!url) return;
  setBusy($("btn-link"), true);
  setMsg("load-msg", "링크의 채널을 확인하는 중…");
  try {
    const video = await api("/api/videos/link", { method: "POST", body: JSON.stringify({ url }) });
    state.videos = [video, ...state.videos.filter((v) => v.video_id !== video.video_id)];
    $("input-link").value = "";
    location.hash = `#/video/${video.video_id}`;
  } catch (e) {
    setMsg("load-msg", e.message, "error");
  } finally {
    setBusy($("btn-link"), false);
  }
}

// 필터: 댓글(yes/no) · 초안(yes/no) · 영상(real/test). "all"이면 거르지 않는다.
function matchesFilters(v) {
  const { comment, draft, kind } = state.filters;
  return (
    (comment === "all" || (comment === "yes") === Boolean(v.posted)) &&
    (draft === "all" || (draft === "yes") === Boolean(v.has_draft)) &&
    (kind === "all" || (kind === "test") === Boolean(v.test))
  );
}

function renderList() {
  const query = state.query.trim().toLowerCase();
  const shown = state.videos.filter((v) => (!query || v.title.toLowerCase().includes(query) || v.channel.toLowerCase().includes(query)) && matchesFilters(v));
  const narrowed = query || Object.values(state.filters).some((value) => value !== "all");
  $("list-empty").hidden = state.videos.length > 0;
  $("list-nomatch").hidden = !state.videos.length || shown.length > 0;
  if (state.videos.length) {
    const posted = state.videos.filter((v) => v.posted).length;
    setMsg("load-msg", `영상 ${shown.length}개${narrowed ? ` (전체 ${state.videos.length}개 중)` : ""} · 댓글 단 영상 ${posted}개`, "ok");
  }
  $("video-list").replaceChildren(
    ...shown.map((v) => {
      const card = el(
        "li",
        { className: "video-card" },
        el("img", { src: v.thumbnail, alt: "", loading: "lazy" }),
        el("div", { className: "title", textContent: v.title }),
        el("div", { className: "meta", textContent: `${v.channel} · ${day(v.published)}` }),
        videoBadges(v),
      );
      card.addEventListener("click", () => (location.hash = `#/video/${v.video_id}`));
      return card;
    }),
  );
}

// ---------- 상세 ----------
async function openDetail(videoId) {
  if (!state.videos.length) await loadVideos(); // 새로고침 등으로 목록이 비어 있으면 먼저 불러온다
  const video = state.videos.find((v) => v.video_id === videoId);
  if (!video) {
    location.hash = "#/";
    return;
  }
  state.current = video;
  const history = await api("/api/history");
  if (state.current !== video) return; // 그 사이 다른 화면으로 이동했다
  const records = history.filter((r) => r.video_id === videoId);
  video.posted = records.some((r) => r.status === "success");

  $("d-title").textContent = video.title;
  $("d-meta").textContent = `${video.channel} · ${day(video.published)}`;
  $("d-link").href = `https://www.youtube.com/watch?v=${video.video_id}`;
  $("d-badges").replaceChildren(...videoBadges(video).children);
  if ($("d-player").dataset.id !== videoId) {
    $("d-player").dataset.id = videoId;
    $("d-player").src = `https://www.youtube.com/embed/${videoId}`;
  }

  $("d-compose").hidden = video.posted;
  $("d-record").hidden = !video.posted;
  if (video.posted) {
    renderRecords(records);
  } else {
    resetPost();
    await loadDraft(video);
  }
}

function renderRecords(records) {
  $("d-records").replaceChildren(
    ...[...records].reverse().map((r) => {
      const links = el("div", { className: "links" });
      if (r.comment_url) links.append(el("a", { href: r.comment_url, target: "_blank", rel: "noopener", textContent: "댓글 보기 ↗" }));
      if (r.screenshot) links.append(el("a", { href: `/screenshots/${r.screenshot}`, target: "_blank", rel: "noopener", textContent: "화면 캡처" }));
      return el(
        "li",
        {},
        el("div", { className: "badges" }, el("span", { className: `badge ${r.status === "success" ? "posted" : ""}`, textContent: RESULT[r.status] || r.status }), el("span", { className: "meta", textContent: `${when(r.time)} · ${r.profile || "-"}` })),
        el("p", { className: "comment", textContent: r.comment }),
        r.reason ? el("p", { className: "meta", textContent: r.reason }) : "",
        links,
      );
    }),
  );
}

// 초안 생성 로딩바: 서버가 초안을 한 번에 돌려주므로 보통 걸리는 시간을 기준으로 차오르고, 끝나기 전에는 95%를 넘지 않는다.
const DRAFT_SECONDS = 20;
const loading = { timer: null, run: 0 };

function showLoading(text) {
  const started = Date.now();
  loading.run++;
  clearInterval(loading.timer);
  $("d-loading").hidden = false;
  const tick = () => {
    const seconds = (Date.now() - started) / 1000;
    $("d-bar-fill").style.width = `${95 * (1 - Math.exp(-seconds / (DRAFT_SECONDS / 2)))}%`;
    $("d-loading-text").textContent = `${text} · ${Math.floor(seconds)}초 (보통 ${DRAFT_SECONDS}초 안팎)`;
  };
  tick();
  loading.timer = setInterval(tick, 200);
}

function hideLoading(done = false) {
  clearInterval(loading.timer);
  const run = done ? loading.run : ++loading.run;
  const hide = () => {
    if (loading.run !== run) return; // 그 사이 새 로딩이 시작됐다
    $("d-loading").hidden = true;
    $("d-bar-fill").style.width = "0";
  };
  if (!done) return hide();
  $("d-bar-fill").style.width = "100%";
  setTimeout(hide, 500);
}

async function loadDraft(video, regenerate = false) {
  $("d-worry").textContent = "…";
  $("d-scene").textContent = "…";
  $("d-basis").textContent = "";
  $("d-comment").value = "";
  $("btn-regen").hidden = true;
  const generating = regenerate || (!video.has_draft && state.status?.ai_key);
  hideLoading();
  if (generating) showLoading("AI가 자막과 인기 댓글을 읽고 초안을 만드는 중");
  setMsg("d-msg", generating ? "" : "초안을 불러오는 중…");
  try {
    const draft = await api(`/api/videos/${video.video_id}/draft${regenerate ? "?regenerate=true" : ""}`);
    if (state.current !== video) return; // 그 사이 다른 화면으로 이동했다
    hideLoading(true);
    video.has_draft = true;
    $("d-badges").replaceChildren(...videoBadges(video).children);
    $("d-worry").textContent = draft.worry || "-";
    $("d-scene").textContent = draft.scene || "-";
    const basis = draft.basis || {};
    const source = basis.transcript_chars
      ? `자막 ${basis.transcript_chars.toLocaleString()}자`
      : `${basis.transcript_status === "blocked" ? "자막 일시 차단(유튜브 요청 제한)" : "자막 없음"} · ${basis.scene_images ? `장면 이미지 ${basis.scene_images}장` : "제목·설명"}`;
    $("d-basis").textContent = `· ${source} · 인기 댓글 ${basis.top_comments ?? 0}개 기반`;
    $("d-comment").value = draft.comment || "";
    setMsg("d-msg", draft.problems?.length ? `초안 규칙 위반: ${draft.problems.join(" / ")}` : "", draft.problems?.length ? "error" : "");
  } catch (e) {
    if (state.current !== video) return;
    hideLoading();
    $("d-worry").textContent = "-";
    $("d-scene").textContent = "-";
    setMsg("d-msg", e.message, "error");
  }
  $("btn-regen").hidden = !state.status?.ai_key;
  updateCount();
}

function updateCount() {
  const text = $("d-comment").value;
  const withSpaces = [...text].length;
  const withoutSpaces = [...text.replace(/\s/g, "")].length;
  const brand = text.split(BRAND).length - 1;
  const bad = withSpaces > LIMITS.max || withoutSpaces < LIMITS.min || brand !== 1;
  $("d-count").textContent = [`공백 포함 ${withSpaces}/${LIMITS.max}자`, `공백 제외 ${withoutSpaces}자 (최소 ${LIMITS.min})`, `${BRAND} ${brand}회`].join(" · ");
  $("d-count").classList.toggle("count-bad", text.length > 0 && bad);
  updatePostButton();
}

// ---------- ③ 댓글 달기 ----------
function updatePostButton() {
  const v = state.current;
  $("btn-post").disabled = state.posting || !v || v.posted || !$("d-comment").value.trim();
}

function resetPost() {
  for (const li of $("steps").children) li.className = "";
  setMsg("post-msg", "");
  $("post-problems").replaceChildren();
  $("post-shot").hidden = true;
  updatePostButton();
}

function setSteps(jobState) {
  const order = ["opening", "typing", "posted"];
  const index = order.indexOf(jobState);
  [...$("steps").children].forEach((li, i) => {
    if (jobState === "failed") {
      if (li.classList.contains("active")) li.className = "failed";
      return;
    }
    li.className = i < index || jobState === "posted" ? "done" : i === index ? "active" : "";
  });
}

async function post() {
  const video = state.current;
  resetPost();
  state.posting = true;
  updatePostButton();
  $("steps").scrollIntoView({ block: "center", behavior: "smooth" }); // 진행 단계 · 결과 메시지가 화면 안에 보이게
  try {
    const { job_id, profile } = await api("/api/post", {
      method: "POST",
      body: JSON.stringify({ video_id: video.video_id, comment: $("d-comment").value.trim(), profile: $("sel-profile").value }),
    });
    setMsg("post-msg", `${profile} 프로필로 진행합니다`);
    await poll(job_id, video);
  } catch (e) {
    setMsg("post-msg", e.problems ? "규칙에 맞지 않아 게시하지 않았습니다" : e.message, "error");
    $("post-problems").replaceChildren(...(e.problems || []).map((p) => el("li", { textContent: p })));
    $("post-problems").scrollIntoView({ block: "nearest", behavior: "smooth" });
  } finally {
    state.posting = false;
    updatePostButton();
    refreshStatus();
  }
}

async function poll(jobId, video) {
  for (;;) {
    const job = await api(`/api/jobs/${jobId}`);
    setSteps(job.state);
    if (job.state === "posted") {
      $("comment-link").href = job.comment_url;
      setMsg("post-msg", "게시 완료 — 내 댓글이 영상에 보이는 것까지 확인했습니다", "ok");
      video.posted = true;
      // 완료 단계를 잠깐 보여준 뒤, 이 영상은 기록만 보이는 화면으로 바뀐다
      setTimeout(() => state.current === video && openDetail(video.video_id), 1500);
      return;
    }
    if (job.state === "failed") {
      setMsg("post-msg", job.message, "error");
      if (job.screenshot) {
        $("post-shot").href = `/screenshots/${job.screenshot}`;
        $("post-shot").hidden = false;
      }
      $("post-shot").scrollIntoView({ block: "nearest", behavior: "smooth" });
      return;
    }
    setMsg("post-msg", job.message);
    await new Promise((r) => setTimeout(r, 700));
  }
}

// ---------- 전체 기록 ----------
async function loadHistory() {
  const rows = await api("/api/history");
  $("history-empty").hidden = rows.length > 0;
  $("history-body").replaceChildren(
    ...rows.map((r) => {
      const result = el("td", { className: `result ${r.status}`, textContent: RESULT[r.status] || r.status });
      if (r.comment_url) result.append(" · ", el("a", { href: r.comment_url, target: "_blank", rel: "noopener", textContent: "댓글 보기" }));
      if (r.reason) result.append(el("div", { className: "meta", textContent: r.reason }));
      if (r.screenshot) result.append(el("div", {}, el("a", { href: `/screenshots/${r.screenshot}`, target: "_blank", rel: "noopener", textContent: "화면 캡처" })));
      return el(
        "tr",
        {},
        el("td", { className: "meta", textContent: when(r.time) }),
        el("td", {}, el("a", { href: `#/video/${r.video_id}`, textContent: r.title }), el("div", { className: "meta", textContent: r.channel })),
        el("td", { textContent: r.profile || "-" }),
        el("td", { className: "comment", textContent: r.comment }),
        result,
      );
    }),
  );
}

$("btn-load").addEventListener("click", loadVideos);
$("form-link").addEventListener("submit", addLink);
$("input-search").addEventListener("input", (e) => {
  state.query = e.target.value;
  renderList();
});
$("filters").addEventListener("click", (e) => {
  const button = e.target.closest(".seg button");
  if (!button) return;
  const group = button.closest(".seg");
  state.filters[group.dataset.filter] = button.dataset.value;
  for (const b of group.querySelectorAll("button")) b.classList.toggle("on", b === button);
  renderList();
});
$("d-comment").addEventListener("input", updateCount);
$("btn-regen").addEventListener("click", () => state.current && loadDraft(state.current, true));
$("btn-post").addEventListener("click", post);
window.addEventListener("hashchange", route);
refreshStatus().then(route);
