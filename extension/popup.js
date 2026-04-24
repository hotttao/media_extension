const serverUrlInput = document.getElementById("serverUrl");
const startButton = document.getElementById("startButton");
const stopButton = document.getElementById("stopButton");
const statusLine = document.getElementById("statusLine");
const jobLine = document.getElementById("jobLine");
const errorLine = document.getElementById("errorLine");

function render(state) {
  serverUrlInput.value = state.serverUrl || "http://127.0.0.1:8765";
  statusLine.textContent = `Status: ${state.lastMessage || "Idle"}`;
  jobLine.textContent = `Job: ${state.currentJobId || "-"}`;
  errorLine.textContent = state.lastError || "";
}

async function refresh() {
  const response = await chrome.runtime.sendMessage({ type: "popup:getState" });
  render(response.state);
}

startButton.addEventListener("click", async () => {
  const response = await chrome.runtime.sendMessage({
    type: "popup:start",
    serverUrl: serverUrlInput.value,
  });
  if (response?.state) {
    render(response.state);
  }
});

stopButton.addEventListener("click", async () => {
  const response = await chrome.runtime.sendMessage({ type: "popup:stop" });
  if (response?.state) {
    render(response.state);
  }
});

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "controllerState") {
    render(message.state);
  }
});

refresh();
