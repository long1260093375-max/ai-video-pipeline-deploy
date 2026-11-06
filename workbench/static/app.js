/* Workbench frontend: form -> jobs -> review. Plain fetch, no framework. */
let mode = "topic";
let selectedJob = null;
let selectedChars = [];

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

async function api(path, opts) {
  const r = await fetch(path, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || ("请求失败 " + r.status));
  return d;
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---- mode tabs ---- */
$$(".mode-btn").forEach((b) => {
  b.addEventListener("click", () => {
    $$(".mode-btn").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    mode = b.dataset.mode;
    $$(".mode-panel").forEach((p) => p.classList.add("hidden"));
    $("#panel-" + mode).classList.remove("hidden");
  });
});

/* ---- characters ---- */
async function loadCharacters() {
  const name = $("#template").value;
  const d = await api("/api/templates/" + encodeURIComponent(name) + "/characters");
  const box = $("#characters");
  box.innerHTML = "";
  selectedChars = d.characters.map((c) => c.file);
  d.characters.forEach((c) => {
    const lab = document.createElement("label");
    lab.className = "char";
    lab.innerHTML = '<input type="checkbox" checked data-file="' + esc(c.file) + '">' +
      '<img src="' + esc(c.url) + '" alt="' + esc(c.file) + '">' +
      '<span>' + esc(c.file.replace(".png", "")) + "</span>";
    lab.querySelector("input").addEventListener("change", () => {
      selectedChars = [...document.querySelectorAll("#characters input:checked")]
        .map((i) => i.dataset.file);
    });
    box.appendChild(lab);
  });
}
$("#template").addEventListener("change", loadCharacters);
loadCharacters();

/* ---- create job ---- */
$("#create-btn").addEventListener("click", async () => {
  const msg = $("#create-msg");
  msg.textContent = "";
  const payload = {
    mode,
    template: $("#template").value,
    voice: $("#voice").value,
    font: $("#font").value,
    characters: selectedChars,
  };
  if (mode === "topic") payload.topic = $("#topic").value;
  if (mode === "batch") payload.topics = $("#topics").value;
  if (mode === "copy") {
    payload.title = $("#copy-title").value;
    payload.copy = $("#copy").value;
    payload.end_cards = [$("#end1").value, $("#end2").value];
  }
  if (mode === "existing") {
    payload.script_source = $("#script-source").value;
    payload.stickers_dir = $("#stickers-dir").value;
    payload.details_dir = $("#details-dir").value;
    payload.skip_details = $("#skip-details").value;
  }
  try {
    const d = await api("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    msg.textContent = "已创建 " + d.jobs.length + " 个任务：" +
      d.jobs.map((j) => j.title).join("、");
    refreshJobs();
  } catch (e) {
    msg.textContent = "创建失败：" + e.message;
  }
});

/* ---- job list ---- */
const STAGE_LABEL = {
  queued: "排队", running: "进行中", awaiting_beats: "等你改分句",
  awaiting_understanding: "等你审理解表", awaiting_review: "等你审片",
  approved: "已通过", rejected: "已打回", failed: "失败", interrupted: "已中断",
};

async function refreshJobs() {
  const d = await api("/api/jobs");
  const list = $("#job-list");
  if (!d.jobs.length) { list.innerHTML = '<p class="hint">暂无任务。</p>'; return; }
  list.innerHTML = d.jobs.map((j) => {
    const cls = j.status === "failed" ? "bad" : j.status === "approved" ? "good" : "";
    return '<div class="job ' + cls + '" data-id="' + esc(j.id) + '">' +
      "<b>" + esc(j.title) + "</b> " +
      '<span class="tag">' + esc(STAGE_LABEL[j.status] || j.status) + "</span> " +
      '<span class="tag">' + esc(j.stage || "") + "</span>" +
      (j.batch_group ? ' <span class="tag">批量 ' + esc(j.batch_group) + "</span>" : "") +
      (j.error ? '<div class="err">' + esc(j.error) + "</div>" : "") +
      '<div class="actions">' +
      '<button data-act="review">查看 / 审片</button>' +
      (j.status === "failed" || j.status === "interrupted"
        ? '<button data-act="retry">重试</button>' : "") +
      '<button data-act="del">删除</button>' +
      "</div></div>";
  }).join("");
  list.querySelectorAll(".job").forEach((el) => {
    el.addEventListener("click", (e) => {
      const act = e.target.dataset.act;
      const id = el.dataset.id;
      if (act === "review") openReview(id);
      if (act === "retry") retryJob(id);
      if (act === "del") deleteJob(id);
    });
  });
}

async function retryJob(id) {
  try { await api("/api/jobs/" + id + "/retry", { method: "POST" }); refreshJobs(); }
  catch (e) { alert("重试失败：" + e.message); }
}
async function deleteJob(id) {
  if (!confirm("删除这个任务（含已生成的视频）？")) return;
  try {
    await api("/api/jobs/" + id + "/delete", { method: "POST" });
    if (selectedJob === id) { selectedJob = null; $("#review").classList.add("hidden"); }
    refreshJobs();
  } catch (e) { alert("删除失败：" + e.message); }
}

/* ---- review ---- */
async function openReview(id) {
  selectedJob = id;
  const j = await api("/api/jobs/" + id);
  lastReviewKey = j.status + "|" + j.stage;
  $("#review").classList.remove("hidden");
  $("#review-title").textContent = "— " + j.title + "（" + (STAGE_LABEL[j.status] || j.status) + "）";
  const body = $("#review-body");
  let h = "";

  if (j.status === "awaiting_beats") {
    const beats = (j.draft_beats || []).map((t, i) =>
      '<div class="beat-row"><span>#' + i + '</span>' +
      '<input class="beat-text" value="' + esc(t) + '" style="flex:3">' +
      '<input class="beat-key" value="" placeholder="关键词（2-5字）" style="flex:1"></div>').join("");
    h += '<h3>分句（可改文字和关键词，至少 2 句）</h3>' + beats +
      '<button class="primary" id="submit-beats">确认分句，继续</button>';
  }

  if (j.status === "awaiting_understanding" && j.understanding_draft) {
    const d = j.understanding_draft;
    h += "<h3>理解表草稿（可改，改完点确认才生图）</h3>";
    if (d.characters && d.characters.length) {
      h += '<p class="hint">可用角色：' +
        d.characters.map((c) => esc(c.name) + "（" + esc(c.role) + "）").join("、") + "</p>";
    }
    h += '<table class="utable"><tr><th>句</th><th>场景</th><th>物体</th><th>符号</th><th>生图提示词</th></tr>' +
      d.rows.map((r, i) =>
        '<tr><td>' + esc(r.text) + '</td>' +
        '<td><input class="u-scene" value="' + esc(r.scene) + '"></td>' +
        '<td><input class="u-object" value="' + esc(r.object) + '"></td>' +
        '<td><input class="u-symbol" value="' + esc(r.symbol) + '"></td>' +
        '<td><input class="u-prompt" value="' + esc(r.prompt) + '"></td></tr>').join("") +
      "</table>" +
      '<button class="primary" id="submit-understanding">确认理解表，开始生图</button>';
  }

  if (j.has_video) {
    h += '<h3>成片</h3><video src="/api/jobs/' + esc(id) + '/video" controls preload="metadata"></video>';
    if (j.script) {
      h += '<h3>口播稿</h3><ol>' +
        j.script.beats.map((b) => "<li>" + esc(b.text) + " <span class='hint'>[" + esc(b.key) + "]</span></li>").join("") +
        "</ol>";
    }
    if (j.status === "awaiting_review") {
      h += '<button class="primary" id="approve">通过，可以导出</button> ' +
        '<button id="reject">打回</button>';
    }
    if (j.status === "approved") {
      h += '<a class="primary btn" href="/api/jobs/' + esc(id) + '/export">导出 MP4</a>';
    }
  } else if (j.status === "awaiting_review") {
    h += '<p class="err">成片文件找不到了，请重试该任务。</p>';
  }

  h += "<h3>日志</h3><pre class='log'>" + esc((j.log || []).join("\n")) + "</pre>";
  body.innerHTML = h;

  const sb = $("#submit-beats");
  if (sb) sb.addEventListener("click", async () => {
    const beats = [...document.querySelectorAll(".beat-row")].map((row) => ({
      text: row.querySelector(".beat-text").value,
      key: row.querySelector(".beat-key").value,
    }));
    try {
      await api("/api/jobs/" + id + "/beats", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: j.title, beats, end_cards: ["谢谢观看", "下期再见"] }),
      });
      openReview(id); refreshJobs();
    } catch (e) { alert("提交失败：" + e.message); }
  });
  const su = $("#submit-understanding");
  if (su) su.addEventListener("click", async () => {
    const rows = [...document.querySelectorAll(".utable tr")].slice(1).map((tr, i) => ({
      beat: i,
      text: j.understanding_draft.rows[i].text,
      key: j.understanding_draft.rows[i].key,
      scene: tr.querySelector(".u-scene").value,
      object: tr.querySelector(".u-object").value,
      symbol: tr.querySelector(".u-symbol").value,
      prompt: tr.querySelector(".u-prompt").value,
    }));
    try {
      await api("/api/jobs/" + id + "/understanding", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows }),
      });
      openReview(id); refreshJobs();
    } catch (e) { alert("提交失败：" + e.message); }
  });
  const ap = $("#approve");
  if (ap) ap.addEventListener("click", async () => {
    try { await api("/api/jobs/" + id + "/approve", { method: "POST" }); openReview(id); refreshJobs(); }
    catch (e) { alert("失败：" + e.message); }
  });
  const rj = $("#reject");
  if (rj) rj.addEventListener("click", async () => {
    try { await api("/api/jobs/" + id + "/reject", { method: "POST" }); openReview(id); refreshJobs(); }
    catch (e) { alert("失败：" + e.message); }
  });
}

$("#export-all").addEventListener("click", () => {
  window.location.href = "/api/export_all";
});

refreshJobs();
let lastReviewKey = "";
setInterval(async () => {
  refreshJobs();
  if (!selectedJob) return;
  // Re-render the review panel only when the job's stage actually changed,
  // so typing in the beats/understanding editors is never wiped out.
  try {
    const j = await api("/api/jobs/" + selectedJob);
    const key = j.status + "|" + j.stage;
    if (key !== lastReviewKey) { lastReviewKey = key; openReview(selectedJob); }
  } catch (e) { /* job may have been deleted */ }
}, 5000);
