const $ = (selector) => document.querySelector(selector);

const runForm = document.querySelector("form");
runForm.querySelector(".form-grid")?.insertAdjacentHTML(
  "afterbegin",
  '<label>Inference plugin <input data-option="inference_plugin" value="model" placeholder="model or module.path:ClassName"></label><label>Inference skill <input data-option="inference_skill" value="default" placeholder="default or a skills/*.txt name"></label><label>Preprocessors <input data-option="preprocessors" value="none" placeholder="none, fibonacci"></label><p class="subtitle">The model inference plugin supports Jev decision models and GenAI/chat models through the configured provider workflows.</p>'
);

runForm.addEventListener("submit", async (event) => {
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
