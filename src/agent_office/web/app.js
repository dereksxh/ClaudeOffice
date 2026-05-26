const TOKEN_KEY = "agentOfficeToken";
const authToken = resolveToken();

let state = { machines: [], sessions: [], agents: [], commands: [] };
let selectedSessionId = null;
let activeView = "console";
let socket = null;

const machineList = document.getElementById("machine-list");
const sessionTable = document.getElementById("session-table");
const sessionDetail = document.getElementById("session-detail");
const officeView = document.getElementById("office-view");
const refreshButton = document.getElementById("refresh-button");
const stateSummary = document.getElementById("state-summary");
const connectionStatus = document.getElementById("connection-status");
const activeViewTitle = document.getElementById("active-view-title");
const viewButtons = Array.from(document.querySelectorAll("[data-view-target]"));
const viewScreens = Array.from(document.querySelectorAll(".view-screen"));

const ACTIONS = [
  { action: "append_prompt", label: "Append" },
  { action: "request_report", label: "Report" },
  { action: "continue", label: "Continue" },
];

function headers() {
  return {
    Authorization: `Bearer ${authToken}`,
    "Content-Type": "application/json",
  };
}

function resolveToken() {
  const params = new URLSearchParams(location.search);
  const tokenFromUrl = params.get("token");
  if (tokenFromUrl) {
    localStorage.setItem(TOKEN_KEY, tokenFromUrl);
    history.replaceState(null, "", location.pathname);
    return tokenFromUrl;
  }

  const storedToken = localStorage.getItem(TOKEN_KEY);
  if (storedToken) {
    return storedToken;
  }

  const enteredToken = window.prompt("Agent Office token") || "";
  if (enteredToken) {
    localStorage.setItem(TOKEN_KEY, enteredToken);
  }
  return enteredToken;
}

function sessionKey(session) {
  return `${session.machine_id}:${session.session_id}`;
}

function statusClass(status) {
  return String(status || "unknown").replace(/[^a-z0-9_-]/gi, "-").toLowerCase();
}

function runtimeInitial(runtimeType) {
  return String(runtimeType || "A").slice(0, 1).toUpperCase();
}

function formatTime(value) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setState(nextState) {
  state = {
    machines: nextState.machines || [],
    sessions: nextState.sessions || [],
    agents: nextState.agents || [],
    commands: nextState.commands || [],
  };

  if (!selectedSessionId && state.sessions.length > 0) {
    selectedSessionId = sessionKey(state.sessions[0]);
  }
  if (selectedSessionId && !state.sessions.some((session) => sessionKey(session) === selectedSessionId)) {
    selectedSessionId = state.sessions.length > 0 ? sessionKey(state.sessions[0]) : null;
  }

  render();
}

function setActiveView(viewName) {
  activeView = viewName === "office" ? "office" : "console";
  viewButtons.forEach((button) => {
    const isActive = button.dataset.viewTarget === activeView;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
  viewScreens.forEach((screen) => {
    screen.classList.toggle("active", screen.id === `${activeView}-screen`);
  });
  if (activeViewTitle) {
    activeViewTitle.textContent = activeView === "office" ? "Office" : "Console";
  }
}

async function fetchState() {
  const response = await fetch("/api/state", { headers: headers() });
  if (!response.ok) {
    throw new Error(`State request failed: ${response.status}`);
  }
  setState(await response.json());
}

function renderMachines() {
  machineList.replaceChildren();
  if (state.machines.length === 0) {
    machineList.append(emptyNode("No machines"));
    return;
  }

  state.machines.forEach((machine) => {
    const item = document.createElement("div");
    item.className = "machine-item";
    item.innerHTML = `
      <strong>${escapeHtml(machine.hostname || machine.machine_id)}</strong>
      <span>${escapeHtml(machine.machine_id)}</span>
      <span class="status ${statusClass(machine.health)}">${machine.health || "unknown"}</span>
    `;
    machineList.append(item);
  });
}

function renderSessions() {
  sessionTable.replaceChildren();
  if (state.sessions.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="5" class="empty">No sessions</td>';
    sessionTable.append(row);
    return;
  }

  state.sessions.forEach((session) => {
    const row = document.createElement("tr");
    row.className = sessionKey(session) === selectedSessionId ? "selected" : "";
    row.tabIndex = 0;
    row.addEventListener("click", () => {
      selectedSessionId = sessionKey(session);
      render();
    });
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        selectedSessionId = sessionKey(session);
        render();
      }
    });

    row.append(cell(session.session_id));
    row.append(cell(session.runtime_type || "-"));
    row.append(statusCell(session.status));
    row.append(cell(session.current_task || session.progress_summary || "-"));
    row.append(actionsCell(session));
    sessionTable.append(row);
  });
}

function renderDetail() {
  sessionDetail.replaceChildren();
  const session = state.sessions.find((item) => sessionKey(item) === selectedSessionId);
  if (!session) {
    sessionDetail.append(emptyNode("Select a session"));
    return;
  }

  const commands = state.commands.filter(
    (command) =>
      command.target_session_id === session.session_id && command.target_machine_id === session.machine_id,
  );
  const agents = state.agents.filter(
    (agent) => agent.session_id === session.session_id && agent.machine_id === session.machine_id,
  );
  sessionDetail.innerHTML = `
    <div class="detail-heading">
      <h2>${escapeHtml(session.project_name || session.session_id)}</h2>
      <span class="status ${statusClass(session.status)}">${session.status || "unknown"}</span>
    </div>
    <dl>
      <dt>Machine</dt><dd>${escapeHtml(session.machine_id)}</dd>
      <dt>CWD</dt><dd>${escapeHtml(session.cwd || "-")}</dd>
      <dt>Model</dt><dd>${escapeHtml(session.model || "-")}</dd>
      <dt>Last Event</dt><dd>${formatTime(session.last_event_at)}</dd>
      <dt>Capabilities</dt><dd>${escapeHtml((session.capabilities || []).join(", ") || "-")}</dd>
    </dl>
    <h3>Progress</h3>
    <p>${escapeHtml(session.progress_summary || session.current_task || "-")}</p>
    <h3>Agents</h3>
    <div class="mini-list">${agents.map(renderAgent).join("") || "<span>No agents</span>"}</div>
    <h3>Commands</h3>
    <div class="mini-list">${commands.map(renderCommand).join("") || "<span>No commands</span>"}</div>
  `;
}

function renderOffice() {
  officeView.replaceChildren();
  if (state.sessions.length === 0) {
    officeView.append(emptyNode("No active desks"));
    return;
  }

  const sessionsByMachine = new Map();
  state.machines.forEach((machine) => {
    sessionsByMachine.set(machine.machine_id, { machine, sessions: [] });
  });
  state.sessions.forEach((session) => {
    if (!sessionsByMachine.has(session.machine_id)) {
      sessionsByMachine.set(session.machine_id, {
        machine: { machine_id: session.machine_id, hostname: session.machine_id, health: "unknown" },
        sessions: [],
      });
    }
    sessionsByMachine.get(session.machine_id).sessions.push(session);
  });

  Array.from(sessionsByMachine.values())
    .filter((group) => group.sessions.length > 0)
    .forEach((group, machineIndex) => {
      const building = document.createElement("article");
      building.className = `office-building ${statusClass(group.machine.health)}`;
      building.style.setProperty("--building-delay", `${machineIndex * 90}ms`);

      const floors = document.createElement("div");
      floors.className = "office-floors";

      group.sessions.forEach((session, sessionIndex) => {
        const room = document.createElement("button");
        room.type = "button";
        room.className = [
          "office-room",
          statusClass(session.status),
          sessionKey(session) === selectedSessionId ? "selected" : "",
        ]
          .filter(Boolean)
          .join(" ");
        room.style.setProperty("--desk-delay", `${sessionIndex * 70}ms`);
        room.addEventListener("click", () => {
          selectedSessionId = sessionKey(session);
          render();
        });
        room.innerHTML = `
          <span class="office-window-glow"></span>
          <span class="agent-avatar">${escapeHtml(runtimeInitial(session.runtime_type))}</span>
          <span class="agent-terminal" aria-hidden="true">
            <span></span>
            <span></span>
            <span class="terminal-cursor"></span>
          </span>
          <span class="office-room-copy">
            <strong>${escapeHtml(session.project_name || session.session_id)}</strong>
            <small>${escapeHtml(session.runtime_type || "runtime")} / ${escapeHtml(session.status || "unknown")}</small>
          </span>
        `;
        floors.append(room);
      });

      building.innerHTML = `
        <header class="office-building-header">
          <div>
            <strong>${escapeHtml(group.machine.hostname || group.machine.machine_id)}</strong>
            <small>${escapeHtml(group.machine.machine_id)}</small>
          </div>
          <span class="status ${statusClass(group.machine.health)}">${group.machine.health || "unknown"}</span>
        </header>
      `;
      building.append(floors);
      officeView.append(building);
    });
}

function renderActions(session) {
  const wrapper = document.createElement("div");
  wrapper.className = "actions";

  ACTIONS.forEach(({ action, label }) => {
    if (!session.capabilities || !session.capabilities.includes(action)) {
      return;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      submitCommand(session, action);
    });
    wrapper.append(button);
  });

  if (wrapper.children.length === 0) {
    wrapper.append(emptyNode("-"));
  }
  return wrapper;
}

async function submitCommand(session, action) {
  const payload = {};
  if (action === "append_prompt") {
    const prompt = window.prompt("Prompt to append");
    if (prompt === null || prompt === "") {
      return;
    }
    payload.prompt = prompt;
  }

  const response = await fetch("/api/commands", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      target_machine_id: session.machine_id,
      target_session_id: session.session_id,
      action,
      payload,
      actor: "web",
      audit_metadata: { source: "agent-office-console" },
    }),
  });

  if (!response.ok) {
    throw new Error(`Command request failed: ${response.status}`);
  }
  await fetchState();
}

function connectWebSocket() {
  if (socket) {
    socket.close();
  }

  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  const nextSocket = new WebSocket(`${wsProto}://${location.host}/ws?token=${encodeURIComponent(authToken)}`);
  socket = nextSocket;

  nextSocket.addEventListener("open", () => {
    connectionStatus.textContent = "Live";
  });
  nextSocket.addEventListener("close", () => {
    if (socket !== nextSocket) {
      return;
    }
    connectionStatus.textContent = "Offline";
    setTimeout(connectWebSocket, 1500);
  });
  nextSocket.addEventListener("error", () => {
    connectionStatus.textContent = "Socket error";
  });
  nextSocket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "state" && message.state) {
      setState(message.state);
    }
  });
}

function render() {
  renderMachines();
  renderSessions();
  renderDetail();
  renderOffice();
  stateSummary.textContent = `${state.machines.length} machines / ${state.sessions.length} sessions / ${state.commands.length} commands`;
}

function cell(value) {
  const td = document.createElement("td");
  td.textContent = value || "-";
  return td;
}

function statusCell(value) {
  const td = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = `status ${statusClass(value)}`;
  badge.textContent = value || "unknown";
  td.append(badge);
  return td;
}

function actionsCell(session) {
  const td = document.createElement("td");
  td.append(renderActions(session));
  return td;
}

function emptyNode(text) {
  const item = document.createElement("span");
  item.className = "empty";
  item.textContent = text;
  return item;
}

function renderAgent(agent) {
  return `<span>${escapeHtml(agent.agent_id)} / ${escapeHtml(agent.status || "unknown")}</span>`;
}

function renderCommand(command) {
  return `<span>${escapeHtml(command.action)} / ${escapeHtml(command.status || "queued")}</span>`;
}

refreshButton.addEventListener("click", () => {
  fetchState().catch((error) => {
    connectionStatus.textContent = error.message;
  });
});

viewButtons.forEach((button) => {
  button.addEventListener("click", () => setActiveView(button.dataset.viewTarget));
});

setActiveView(activeView);
fetchState().catch((error) => {
  connectionStatus.textContent = error.message;
});
connectWebSocket();
