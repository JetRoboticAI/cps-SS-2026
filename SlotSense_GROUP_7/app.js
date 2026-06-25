const pubnubConfig = {
  subscribeKey: "sub-c-d2cf210c-9365-4938-ac72-9627d63ef60d",
  publishKey: "pub-c-3a406da1-b0a2-4010-b78f-2334b59a131d",
  uuid: `parksphere-ui-${Math.random().toString(16).slice(2, 10)}`,
};

const channel = "group_7";
const state = {
  slot: null,
  distance: null,
  gate: "Idle",
  lastUpdated: null,
};

const els = {
  slotState: document.getElementById("slotState"),
  slotBadge: document.getElementById("slotBadge"),
  distanceValue: document.getElementById("distanceValue"),
  gateStatus: document.getElementById("gateStatus"),
  lastUpdate: document.getElementById("lastUpdate"),
  commandStatus: document.getElementById("commandStatus"),
  activityLog: document.getElementById("activityLog"),
  clearLogBtn: document.getElementById("clearLogBtn"),
  openBtn: document.getElementById("openBtn"),
  closeBtn: document.getElementById("closeBtn"),
  statusDot: document.getElementById("statusDot"),
  connectionText: document.getElementById("connectionText"),
};

const pubnub = new PubNub(pubnubConfig);

function formatTime(timestamp) {
  return new Intl.DateTimeFormat([], {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(timestamp);
}

function setConnectionStatus(statusText, className) {
  els.connectionText.textContent = statusText;
  els.statusDot.className = "status-dot";
  if (className) {
    els.statusDot.classList.add(className);
  }
}

function renderState() {
  const slot = state.slot || "Waiting for data";
  const badgeClass = !state.slot
    ? "waiting"
    : state.slot.toLowerCase() === "free"
      ? "free"
      : "occupied";

  els.slotState.textContent = slot;
  els.slotBadge.textContent = state.slot || "Waiting";
  els.slotBadge.className = `badge ${badgeClass}`;
  els.distanceValue.textContent = typeof state.distance === "number" ? state.distance.toFixed(2) : "--";
  els.gateStatus.textContent = state.gate || "Idle";
  els.lastUpdate.textContent = state.lastUpdated
    ? `Last update at ${formatTime(state.lastUpdated)}`
    : "Waiting for ultrasonic and IR sensor updates from Raspberry Pi.";
}

function addLogEntry(text) {
  const placeholder = els.activityLog.querySelector(".log-placeholder");
  if (placeholder) {
    placeholder.remove();
  }

  const item = document.createElement("li");
  const time = document.createElement("span");
  const message = document.createElement("span");

  time.className = "log-time";
  time.textContent = formatTime(new Date());
  message.textContent = text;

  item.appendChild(time);
  item.appendChild(message);
  els.activityLog.prepend(item);

  while (els.activityLog.children.length > 12) {
    els.activityLog.removeChild(els.activityLog.lastChild);
  }
}

function updateFromSensorMessage(message) {
  state.slot = message.slot || state.slot;
  state.distance = typeof message.distance === "number" ? message.distance : state.distance;
  state.gate = message.gate || state.gate;
  state.lastUpdated = new Date();
  renderState();

  const summary = `Slot ${state.slot || "Unknown"}, gate ${state.gate || "Idle"}, distance ${
    typeof state.distance === "number" ? `${state.distance.toFixed(2)} cm` : "unavailable"
  }, IR gate logic active.`;
  addLogEntry(summary);
}

function publishCommand(command, label) {
  els.commandStatus.textContent = `Sending ${label.toLowerCase()} command...`;

  pubnub.publish(
    {
      channel,
      message: { command },
    },
    (status) => {
      if (status?.error) {
        els.commandStatus.textContent = `Could not send ${label.toLowerCase()} command.`;
        addLogEntry(`Failed to publish command: ${label}.`);
        return;
      }

      els.commandStatus.textContent = `${label} command sent successfully.`;
      addLogEntry(`Remote command sent: ${label}.`);
    }
  );
}

pubnub.addListener({
  status(event) {
    if (event.category === "PNConnectedCategory") {
      setConnectionStatus("Connected", "connected");
      addLogEntry("Dashboard connected to PubNub.");
    } else if (event.error) {
      setConnectionStatus("Connection issue", "disconnected");
    }
  },
  message(event) {
    const message = event.message || {};

    if ("slot" in message || "distance" in message || "gate" in message) {
      updateFromSensorMessage(message);
    }

    if ("command" in message) {
      addLogEntry(`Incoming command observed: ${message.command}.`);
    }
  },
});

els.openBtn.addEventListener("click", () => publishCommand("force_open", "Force Open"));
els.closeBtn.addEventListener("click", () => publishCommand("force_close", "Force Close"));
els.clearLogBtn.addEventListener("click", () => {
  els.activityLog.innerHTML = '<li class="log-placeholder">Live messages will appear here.</li>';
});

setConnectionStatus("Connecting...", "");
renderState();
pubnub.subscribe({ channels: [channel] });
