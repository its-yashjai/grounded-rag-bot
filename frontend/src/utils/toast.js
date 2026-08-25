export function showToast(message, type = "success") {
  const el = document.createElement("div");
  el.className = `upload-toast ${type}`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translate(-50%, -10px)";
    el.style.transition = "opacity 0.3s, transform 0.3s";
    setTimeout(() => el.remove(), 300);
  }, type === "loading" ? 2000 : 3000);
  return el;
}

export function showUploadToast(files) {
  const names = Array.from(files).map(f => f.name).join(", ");
  return showToast(`Uploading ${files.length} file${files.length > 1 ? "s" : ""} — ${names}`, "loading");
}

export function showSuccessToast(text) {
  return showToast(text, "success");
}

export function showErrorToast(text) {
  return showToast(text, "error");
}
