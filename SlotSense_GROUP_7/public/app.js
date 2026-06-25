const socket = io();

const els = {
  nodeLight: document.getElementById("nodeLight"),
  nodeState: document.getElementById("nodeState"),
  gateBadge: document.getElementById("gateBadge"),
  gateArm: document.getElementById("gateArm"),
  gateTitle: document.getElementById("gateTitle"),
  gateReason: document.getElementById("gateReason"),
  carIcon: document.getElementById("carIcon"),
  slotBadge: document.getElementById("slotBadge"),
  spaceIndicator: document.getElementById("spaceIndicator"),
  distanceValue: document.getElementById("distanceValue"),
  gateDistanceValue: document.getElementById("gateDistanceValue"),
  ledState: document.getElementById("ledState"),
  servoAngle: document.getElementById("servoAngle"),
  activityLog: document.getElementById("activityLog"),
  openBtn: document.getElementById("openBtn"),
  closeBtn: document.getElementById("closeBtn"),
  autoBtn: document.getElementById("autoBtn"),
  clearLogBtn: document.getElementById("clearLogBtn"),
};

let lastEventText = "";

function titleCase(value) {
  return String(value || "waiting")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function addLog(text) {
  if (!text || text === lastEventText) return;
  lastEventText = text;

  if (els.activityLog.children.length === 1 && els.activityLog.textContent.includes("Waiting")) {
    els.activityLog.innerHTML = "";
  }

  const item = document.createElement("li");
  item.textContent = `${new Date().toLocaleTimeString()} - ${text}`;
  els.activityLog.prepend(item);

  while (els.activityLog.children.length > 12) {
    els.activityLog.removeChild(els.activityLog.lastElementChild);
  }
}

function render(state) {
  const slots = Object.values(state.slots || {});
  const slot = state.slots?.A1 || slots[0] || {};
  const gate = state.gate || {};
  const nodeOnline = state.node === "online";
  const gateOpen = String(gate.state || "").toLowerCase().includes("open");
  const slotState = String(slot.state || "").toLowerCase();
  const occupied = Boolean(slot.occupied) || slotState === "occupied";
  const available = Boolean(slot.space_available) || ["available", "vacant", "free"].includes(slotState);

  els.nodeLight.classList.toggle("online", nodeOnline);
  els.nodeState.textContent = state.node || "offline";

  els.gateBadge.textContent = titleCase(gate.state || "closed");
  els.gateArm.classList.toggle("open", gateOpen);
  els.carIcon.classList.toggle("detected", Boolean(gate.car_detected));
  els.gateTitle.textContent = gateOpen ? "Gate is open" : "Gate is closed";
  els.gateReason.textContent = gate.reason || "Waiting for the Raspberry Pi to publish gate status.";
  els.servoAngle.textContent = Math.round(Number(gate.servo_angle || 0));
  els.gateDistanceValue.textContent = typeof gate.gate_distance_cm === "number" ? gate.gate_distance_cm.toFixed(1) : "--";

  els.slotBadge.textContent = slot.state ? titleCase(slot.state) : "Waiting";
  els.spaceIndicator.classList.toggle("occupied", occupied);
  els.spaceIndicator.classList.toggle("available", available);
  els.distanceValue.textContent = typeof slot.distance_cm === "number" ? slot.distance_cm.toFixed(1) : "--";
  els.ledState.textContent = slot.led_on || available ? "On" : occupied ? "Off" : "--";

  if (state.lastEvent) {
    addLog(state.lastEvent.text);
  }
}

function sendCommand(command) {
  socket.emit("gate-command", command);
  addLog(`Web command sent: ${titleCase(command)}`);
}

socket.on("state", render);
socket.on("connect", () => addLog("Web dashboard connected to local bridge"));
socket.on("disconnect", () => addLog("Web dashboard disconnected from local bridge"));

els.openBtn.addEventListener("click", () => sendCommand("force_open"));
els.closeBtn.addEventListener("click", () => sendCommand("force_close"));
els.autoBtn.addEventListener("click", () => sendCommand("auto"));
els.clearLogBtn.addEventListener("click", () => {
  lastEventText = "";
  els.activityLog.innerHTML = "<li>Waiting for MQTT messages.</li>";
});
