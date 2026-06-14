const form = document.querySelector("#chat-composer");
const transcript = document.querySelector("#chat-transcript");
const questionBox = document.querySelector("#question");
const sessionId = sessionStorage.getItem("rise_session") || crypto.randomUUID();
sessionStorage.setItem("rise_session", sessionId);

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  })[char]);
}

function scrollToLatest() {
  window.requestAnimationFrame(() => window.scrollTo({top: document.body.scrollHeight, behavior: "smooth"}));
}

function sourceLink(source) {
  if (!source) return "";
  return `<a href="/api/sources/${encodeURIComponent(source.doc_id)}/pdf" target="_blank" rel="noopener">${escapeHtml(source.filename)}</a>`;
}

function topicCard(topic) {
  const sources = [topic.agenda_document, ...(topic.minutes_documents || [])].filter(Boolean);
  const summary = topic.summary ? `<p><strong>Summary:</strong> ${escapeHtml(topic.summary)}</p>` : "";
  return `<article class="topic">
    <p class="eyebrow">${escapeHtml(topic.meeting_date)} · ${escapeHtml(topic.verification_status)}</p>
    <h3>${escapeHtml(topic.title)}</h3>
    <p>${escapeHtml(topic.verification_reason || "")}</p>${summary}
    <p class="source-links">${sources.map(sourceLink).join(" · ")}</p>
  </article>`;
}

function personProfile(profile) {
  if (!profile) return "";
  const roles = (profile.roles || []).map(role =>
    `<li><strong>${escapeHtml(role.years.join(", "))}</strong><span>${escapeHtml(role.role)}</span></li>`
  ).join("");
  const active = (profile.active_mentions || []).slice(0, 10).map(item =>
    `<article class="evidence-line"><strong>${escapeHtml(item.meeting_date)}</strong><p>${escapeHtml(item.excerpt)}</p><a href="/api/sources/${encodeURIComponent(item.doc_id)}/pdf" target="_blank" rel="noopener">${escapeHtml(item.filename)}</a></article>`
  ).join("");
  const currentRole = profile.current_role
    ? `<p><strong>Current verified role:</strong> ${escapeHtml(profile.current_role.role)} <span class="muted">(${escapeHtml(profile.current_role.meeting_date)}, ${sourceLink(profile.current_role)})</span></p>`
    : `<p>No verified current role was identified in the indexed corpus.</p>`;
  return `<section class="profile-panel">
    ${currentRole}
    <div class="metric-row">
      <div><strong>${profile.mention_doc_count}</strong><span>documents mentioning this person</span></div>
      <div><strong>${profile.active_doc_count}</strong><span>active participation records</span></div>
      <div><strong>${profile.attendance_only_doc_count}</strong><span>role, attendance, or absence records</span></div>
    </div>
    <details><summary>Role history (${(profile.roles || []).length})</summary><ol class="role-timeline">${roles || "<li>No role title was identified.</li>"}</ol></details>
    <details><summary>Active participation evidence (${profile.active_doc_count})</summary><div>${active || "<p>No explicit active participation was identified.</p>"}</div></details>
  </section>`;
}

function peopleSummary(people) {
  if (!people?.length) return "";
  return `<details class="people-results" open><summary>People identified in confirmed evidence (${people.length})</summary>
    <div>${people.map(person => `<article class="person-result"><h3>${escapeHtml(person.name)}</h3><p>${person.topic_ids.length} confirmed topic(s)</p></article>`).join("")}</div>
  </details>`;
}

function assistantMarkup(data) {
  const response = data.response;
  const coverage = response.year_coverage || {};
  const corpusCoverage = coverage.corpus?.from ? `${coverage.corpus.from}–${coverage.corpus.to}` : "Unavailable";
  const confirmedCoverage = coverage.confirmed?.from ? `${coverage.confirmed.from}–${coverage.confirmed.to}` : "No confirmed years";
  const pendingSummaries = data.confirmed_topics.filter(topic => topic.summary_status !== "completed").length;
  const summaryAction = pendingSummaries
    ? `<button class="summarize" type="button">Summarize next ${Math.min(10, pendingSummaries)} results</button>`
    : "";
  return `<article class="message assistant-message" data-inquiry-id="${escapeHtml(data.inquiry_id)}">
    <p class="eyebrow">Direct answer</p>
    <h2>${escapeHtml(response.conclusion)}</h2>
    ${response.answer_explanation ? `<p>${escapeHtml(response.answer_explanation)}</p>` : ""}
    ${response.answer_confidence ? `<p class="confidence">RISE confidence: ${escapeHtml(response.answer_confidence)}. Review the verified evidence below.</p>` : ""}
    ${personProfile(response.person_profile)}
    ${peopleSummary(data.people)}
    <section class="retrieval-summary">
      <p class="eyebrow">Verified retrieval summary</p>
      <p>${escapeHtml(response.result_summary)}</p>
      <p>${escapeHtml(response.searched_scope)}</p>
      <p class="coverage"><strong>Corpus coverage:</strong> ${escapeHtml(corpusCoverage)} · <strong>Confirmed result coverage:</strong> ${escapeHtml(confirmedCoverage)}</p>
      <div class="counts"><strong>${response.verified_count} confirmed</strong><span>${response.possible_count} possible</span></div>
      <div class="message-actions">
        <select class="sort-select" aria-label="Sort results">
          <option value="relevance" ${data.sort_order === "relevance" ? "selected" : ""}>Relevance</option>
          <option value="chronological_desc" ${data.sort_order === "chronological_desc" ? "selected" : ""}>Newest first</option>
        </select>
        ${summaryAction}
      </div>
    </section>
    <details class="supporting-results"><summary>Supporting files (${response.verified_count})</summary><div class="confirmed-results">${data.confirmed_topics.map(topicCard).join("")}</div></details>
    <details><summary>Possible results (${response.possible_count})</summary><div>${data.possible_topics.map(topicCard).join("")}</div></details>
    <details><summary>Retrieval audit</summary><pre>${escapeHtml(JSON.stringify(response.retrieval_audit, null, 2))}</pre></details>
  </article>`;
}

function appendUserMessage(text) {
  transcript.insertAdjacentHTML("beforeend", `<article class="message user-message"><p>${escapeHtml(text)}</p></article>`);
}

function appendThinking() {
  const id = `thinking-${crypto.randomUUID()}`;
  transcript.insertAdjacentHTML("beforeend", `<article id="${id}" class="message assistant-message thinking"><span></span><p>Searching complete UAC documents and verifying evidence...</p></article>`);
  return document.querySelector(`#${id}`);
}

function replaceInquiryMessage(data) {
  const existing = transcript.querySelector(`[data-inquiry-id="${CSS.escape(data.inquiry_id)}"]`);
  if (existing) existing.outerHTML = assistantMarkup(data);
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const question = questionBox.value.trim();
  if (!question) return;
  appendUserMessage(question);
  questionBox.value = "";
  const thinking = appendThinking();
  scrollToLatest();

  try {
    const response = await fetch("/api/inquiries/stream", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session_id: sessionId, question})
    });
    if (!response.ok) throw new Error(await response.text());
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const events = buffer.split("\n\n");
      buffer = events.pop();
      for (const eventBlock of events) {
        const eventName = eventBlock.match(/^event: (.+)$/m)?.[1];
        const raw = eventBlock.match(/^data: (.+)$/m)?.[1];
        if (!raw) continue;
        const data = JSON.parse(raw);
        if (eventName === "status") thinking.querySelector("p").textContent = data.message;
        if (eventName === "result") thinking.outerHTML = assistantMarkup(data);
      }
    }
  } catch (error) {
    thinking.classList.add("error");
    thinking.querySelector("p").textContent = `Inquiry failed: ${error.message}`;
  }
  scrollToLatest();
});

questionBox.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});

transcript.addEventListener("change", async event => {
  if (!event.target.matches(".sort-select")) return;
  const message = event.target.closest("[data-inquiry-id]");
  const response = await fetch(`/api/inquiries/${message.dataset.inquiryId}/sort`, {
    method: "PATCH", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({sort_order: event.target.value})
  });
  replaceInquiryMessage(await response.json());
});

transcript.addEventListener("click", async event => {
  if (!event.target.matches(".summarize")) return;
  const message = event.target.closest("[data-inquiry-id]");
  event.target.disabled = true;
  event.target.textContent = "Summarizing...";
  const response = await fetch(`/api/inquiries/${message.dataset.inquiryId}/continue-summaries`, {method: "POST"});
  const data = await response.json();
  replaceInquiryMessage(data.inquiry);
  scrollToLatest();
});

document.querySelector("#new-chat").addEventListener("click", async () => {
  await fetch(`/api/sessions/${sessionId}/reset`, {method: "POST"});
  sessionStorage.removeItem("rise_session");
  window.location.reload();
});
