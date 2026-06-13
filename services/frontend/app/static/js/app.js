const form = document.querySelector("#inquiry-form");
const statusBox = document.querySelector("#status");
const answer = document.querySelector("#answer");
const sessionId = sessionStorage.getItem("rise_session") || crypto.randomUUID();
sessionStorage.setItem("rise_session", sessionId);
let currentInquiry = null;

function sourceLink(source) {
  if (!source) return "";
  return `<a href="/api/sources/${encodeURIComponent(source.doc_id)}/pdf" target="_blank">${source.filename}</a>`;
}

function topicCard(topic) {
  const sources = [topic.agenda_document, ...(topic.minutes_documents || [])].filter(Boolean);
  const summary = topic.summary ? `<p><strong>Summary:</strong> ${topic.summary}</p>` : "";
  return `<article class="topic"><p class="eyebrow">${topic.meeting_date} · ${topic.verification_status}</p><h3>${topic.title}</h3><p>${topic.verification_reason || ""}</p>${summary}<p>${sources.map(sourceLink).join(" · ")}</p></article>`;
}

function render(data) {
  currentInquiry = data;
  const response = data.response;
  document.querySelector("#conclusion").textContent = response.conclusion;
  document.querySelector("#scope").textContent = response.searched_scope;
  document.querySelector("#confirmed-count").textContent = `${response.verified_count} confirmed`;
  document.querySelector("#possible-count").textContent = `${response.possible_count} possible`;
  document.querySelector("#confirmed").innerHTML = data.confirmed_topics.map(topicCard).join("");
  document.querySelector("#possible").innerHTML = data.possible_topics.map(topicCard).join("");
  document.querySelector("#audit").textContent = JSON.stringify(response.retrieval_audit, null, 2);
  answer.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusBox.textContent = "Searching complete UAC documents and verifying evidence...";
  answer.hidden = true;
  const response = await fetch("/api/inquiries", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({session_id: sessionId, question: document.querySelector("#question").value})
  });
  if (!response.ok) { statusBox.textContent = await response.text(); return; }
  render(await response.json());
  statusBox.textContent = "";
});

document.querySelector("#sort").addEventListener("change", async (event) => {
  if (!currentInquiry) return;
  const response = await fetch(`/api/inquiries/${currentInquiry.inquiry_id}/sort`, {
    method: "PATCH", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({sort_order: event.target.value})
  });
  render(await response.json());
});

document.querySelector("#summarize").addEventListener("click", async () => {
  if (!currentInquiry) return;
  statusBox.textContent = "Summarizing the next result batch...";
  const response = await fetch(`/api/inquiries/${currentInquiry.inquiry_id}/continue-summaries`, {method: "POST"});
  const data = await response.json();
  render(data.inquiry);
  statusBox.textContent = data.remaining ? `${data.remaining} confirmed results remain to summarize.` : "All confirmed results are summarized.";
});
