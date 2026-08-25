const BASE = "";

export async function uploadDocuments(files) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const res = await fetch(`${BASE}/api/v1/documents/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error((await res.json()).detail || "Upload failed");
  return res.json();
}
export async function listDocuments() {
  const res = await fetch(`${BASE}/api/v1/documents`);
  return res.json();
}
export async function deleteDocument(id) {
  return fetch(`${BASE}/api/v1/documents/${id}`, { method: "DELETE" });
}
export async function listConversations() {
  const res = await fetch(`${BASE}/api/v1/conversations`);
  return res.json();
}
export async function getConversation(id) {
  const res = await fetch(`${BASE}/api/v1/conversations/${id}`);
  if (!res.ok) return null;
  return res.json();
}
export async function createConversation(title = "New chat") {
  const res = await fetch(`${BASE}/api/v1/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  return res.json();
}
export async function deleteConversation(id) {
  return fetch(`${BASE}/api/v1/conversations/${id}`, { method: "DELETE" });
}
export async function streamChat(message, documentIds, conversationId, { onConversation, onCitations, onToken, onDone, onError, signal }) {
  let gotDone = false
  try {
    const res = await fetch(`${BASE}/api/v1/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, document_ids: documentIds, conversation_id: conversationId ?? null }),
      signal,
    });
    if (!res.ok || !res.body) throw new Error("Request failed");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop();
      for (const raw of events) {
        if (!raw.trim()) continue;
        const lines = raw.split("\n");
        const eventLine = lines.find(l => l.startsWith("event:"));
        const dataLine = lines.find(l => l.startsWith("data:"));
        if (!eventLine || !dataLine) continue;
        const eventName = eventLine.replace("event:", "").trim();
        const data = JSON.parse(dataLine.replace("data:", "").trim());
        if (eventName === "conversation") onConversation?.(data.conversation_id);
        if (eventName === "citations") onCitations?.(data.citations);
        if (eventName === "token") onToken?.(data.delta);
        if (eventName === "done") { gotDone = true; onDone?.(data); }
      }
    }
    if (!gotDone && !signal?.aborted) {
      // Stream closed without done (e.g., LLM error) — surface as error so UI doesn't hang on "Generating..."
      throw new Error("Stream ended unexpectedly");
    }
  } catch (err) {
    if (err?.name === "AbortError") onError?.(err);
    else if (!gotDone) onError?.(err);
  }
}
