const $ = (selector) => document.querySelector(selector);

document.querySelector("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const fields = [...document.querySelectorAll("[data-option]")];
  const payload = Object.fromEntries(fields.map((field) => [field.dataset.option, field.type === "checkbox" ? field.checked : field.value]));
  payload.mode = document.body.dataset.mode;
  payload.symbols = [...$("#symbolChoices").selectedOptions].map((option) => option.value);
  const message = $("#formMessage");
  if (!payload.symbols.length) { message.textContent = "Choose a symbol first."; return; }
  message.textContent = "Starting…";
  try {
    const response = await fetch("/api/run", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    const result = await response.json();
    message.textContent = result.message;
  } catch { message.textContent = "Unable to contact the local dashboard server."; }
});
