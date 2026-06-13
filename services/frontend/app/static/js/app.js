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

function personCard(person) {
  return `<article class="topic"><p class="eyebrow">Person summary</p><h3>${person.name}</h3><p>${person.topic_ids.length} related agenda topics</p><p>Aliases: ${(person.aliases || []).join(", ")}</p></article>`;
}

function render(data) {
  currentInquiry = data;
  const response = data.response;
  document.querySelector("#conclusion").textContent = response.conclusion;
  document.querySelector("#explanation").textContent = response.answer_explanation || "";
  document.querySelector("#confidence").textContent = response.answer_confidence ? `RISE confidence: ${response.answer_confidence}. Review the verified evidence below.` : "";
  document.querySelector("#result-summary").textContent = response.result_summary;
  document.querySelector("#scope").textContent = response.searched_scope;
  document.querySelector("#confirmed-count").textContent = `${response.verified_count} confirmed`;
  document.querySelector("#possible-count").textContent = `${response.possible_count} possible`;
  document.querySelector("#confirmed").innerHTML = data.confirmed_topics.map(topicCard).join("");
  document.querySelector("#people").innerHTML = (data.people || []).map(personCard).join("");
  document.querySelector("#possible").innerHTML = data.possible_topics.map(topicCard).join("");
  document.querySelector("#audit").textContent = JSON.stringify(response.retrieval_audit, null, 2);
  answer.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusBox.textContent = "Searching complete UAC documents and verifying evidence...";
  answer.hidden = true;
  const response = await fetch("/api/inquiries/stream", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({session_id: sessionId, question: document.querySelector("#question").value})
  });
  if (!response.ok) { statusBox.textContent = await response.text(); return; }
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
      const event = eventBlock.match(/^event: (.+)$/m)?.[1];
      const raw = eventBlock.match(/^data: (.+)$/m)?.[1];
      if (!raw) continue;
      const data = JSON.parse(raw);
      if (event === "status") statusBox.textContent = data.message;
      if (event === "result") render(data);
    }
  }
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
