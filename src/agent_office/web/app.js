const TOKEN_KEY = "agentOfficeToken";
const authToken = resolveToken();

let state = { machines: [], sessions: [], agents: [], token_usage: [], commands: [] };
let selectedSessionId = null;
let activeView = "console";
let socket = null;
const officeRuntimeNodes = new Map();
const officeDeskNodes = new Map();
const officeBehaviorState = new Map();
const RUNTIME_ORDER = ["codex", "hermes", "claude_code"];
const IDLE_ACTIVITIES = ["sleeping", "phone", "chatting"];
const WAITING_SPRITE_STATUSES = new Set(["waiting_permission", "waiting_input", "blocked", "starting", "waiting"]);
const OFFICE_WALK_MS = 2200;
const OFFICE_BEHAVIOR_SLOT_MS = 60000;
let officeRenderTimer = null;

const machineList = document.getElementById("machine-list");
const sessionTable = document.getElementById("session-table");
const sessionDetail = document.getElementById("session-detail");
const officeView = document.getElementById("office-view");
const refreshButton = document.getElementById("refresh-button");
const stateSummary = document.getElementById("state-summary");
const connectionStatus = document.getElementById("connection-status");
const activeViewTitle = document.getElementById("active-view-title");
const tokenUsageSummary = document.getElementById("token-usage-summary");
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
  return String(status || "unknown").replaceAll("_", "-").replace(/[^a-z0-9-]/gi, "-").toLowerCase();
}

function runtimeInitial(runtimeType) {
  return String(runtimeType || "A").slice(0, 1).toUpperCase();
}

function runtimeTypeLabel(runtimeType) {
  const labels = {
    codex: "Codex",
    hermes: "Hermes",
    claude_code: "Claude Code",
  };
  return labels[runtimeType] || String(runtimeType || "Other");
}

function mascotForRuntime(runtimeType) {
  if (runtimeType === "codex") {
    return "mascot-cow";
  }
  if (runtimeType === "hermes") {
    return "mascot-pony";
  }
  return "mascot-helper";
}

function officeSpriteCharacter(runtimeType) {
  if (runtimeType === "hermes") {
    return "pony";
  }
  return "calf";
}

function officeSpriteActivity(session, idleActivity) {
  if (idleActivity === "walk") {
    return "walk";
  }
  if (session.status === "working") {
    return "typing";
  }
  if (WAITING_SPRITE_STATUSES.has(String(session.status || ""))) {
    return "waiting";
  }
  if (idleActivity === "sleeping") {
    return "idle-sleep";
  }
  if (idleActivity === "phone") {
    return "idle-phone";
  }
  if (idleActivity === "chatting") {
    return "idle-chat";
  }
  return "stand";
}

function stableHash(value) {
  let hash = 0;
  for (const char of String(value || "")) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return hash;
}

function idleActivityForSession(session) {
  const index = stableHash(sessionKey(session)) % IDLE_ACTIVITIES.length;
  return IDLE_ACTIVITIES[index];
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function officeDeskPosition(runtimeType, sessionIndex) {
  const configs = {
    codex: { x: 10, y: 24, columns: 5, xStep: 16, yStep: 14 },
    hermes: { x: 12, y: 71, columns: 4, xStep: 18, yStep: 10 },
    claude_code: { x: 60, y: 70, columns: 3, xStep: 14, yStep: 10 },
    other: { x: 66, y: 26, columns: 3, xStep: 12, yStep: 12 },
  };
  const config = configs[runtimeType] || configs.other;
  const column = sessionIndex % config.columns;
  const row = Math.floor(sessionIndex / config.columns);
  return {
    place: "desk",
    x: clamp(config.x + column * config.xStep + (row % 2) * 3, 8, 92),
    y: clamp(config.y + row * config.yStep, 18, 86),
  };
}

function officeLoungePosition(loungeIndex, memberIndex, memberCount) {
  const lounges = [
    { place: "lounge", label: "休息室", x: 72, y: 25 },
    { place: "lounge", label: "茶水区", x: 80, y: 53 },
    { place: "lounge", label: "沙发区", x: 58, y: 76 },
  ];
  const lounge = lounges[loungeIndex % lounges.length];
  const spread = memberCount > 1 ? memberIndex - (memberCount - 1) / 2 : 0;
  return {
    place: lounge.place,
    label: lounge.label,
    x: clamp(lounge.x + spread * 7, 8, 92),
    y: clamp(lounge.y + (memberIndex % 2) * 4, 18, 86),
  };
}

function officeIdlePlans(sessionsByRuntime, now) {
  const plans = new Map();
  const slot = Math.floor(now / OFFICE_BEHAVIOR_SLOT_MS);
  for (const [runtimeType, sessions] of sessionsByRuntime) {
    const idleSessions = sessions
      .filter((session) => session.status === "idle")
      .sort((left, right) => sessionKey(left).localeCompare(sessionKey(right)));
    const chatMembers = new Set();
    if (idleSessions.length >= 2) {
      const groupSize = Math.min(3, idleSessions.length);
      const startIndex = stableHash(`${runtimeType}:${slot}:chat`) % idleSessions.length;
      for (let index = 0; index < groupSize; index += 1) {
        chatMembers.add(sessionKey(idleSessions[(startIndex + index) % idleSessions.length]));
      }
    }
    let chatIndex = 0;
    idleSessions.forEach((session) => {
      const key = sessionKey(session);
      if (chatMembers.has(key)) {
        const memberIndex = chatIndex;
        chatIndex += 1;
        plans.set(key, {
          activity: "chatting",
          place: "lounge",
          loungeIndex: stableHash(`${runtimeType}:${slot}:lounge`) % 3,
          memberIndex,
          memberCount: chatMembers.size,
        });
        return;
      }
      const soloActivities = ["sleeping", "phone"];
      plans.set(key, {
        activity: soloActivities[stableHash(`${key}:${slot}:activity`) % soloActivities.length],
        place: stableHash(`${key}:${slot}:place`) % 3 === 0 ? "lounge" : "desk",
        loungeIndex: stableHash(`${key}:${slot}:lounge`) % 3,
        memberIndex: 0,
        memberCount: 1,
      });
    });
  }
  return plans;
}

function scheduleOfficeRender(delayMs) {
  if (officeRenderTimer !== null) {
    clearTimeout(officeRenderTimer);
  }
  officeRenderTimer = setTimeout(() => {
    officeRenderTimer = null;
    if (activeView === "office") {
      renderOffice();
    }
  }, Math.max(120, delayMs));
}

function officeBehaviorForSession(session, sessionIndex, idlePlans, now) {
  const deskPosition = officeDeskPosition(session.runtime_type, sessionIndex);
  const key = sessionKey(session);
  const previous = officeBehaviorState.get(key) || {};
  let target = deskPosition;
  let activity = session.status === "working" ? "typing" : idleActivityForSession(session);
  if (session.status === "idle") {
    const plan = idlePlans.get(key);
    activity = plan?.activity || activity;
    if (plan?.place === "lounge") {
      target = officeLoungePosition(plan.loungeIndex, plan.memberIndex, plan.memberCount);
    }
  }

  const walkFrom = previous.position || target;
  const targetKey = `${target.place}:${Math.round(target.x)}:${Math.round(target.y)}:${session.status}`;
  let walkUntil = Number(previous.walkUntil || 0);
  if (session.status === "working" && previous.status && previous.status !== "working") {
    if (previous.targetKey !== targetKey || walkUntil <= now) {
      walkUntil = now + OFFICE_WALK_MS;
    }
  }

  const walkingToDesk = session.status === "working" && walkUntil > now;
  if (walkingToDesk) {
    activity = "walk";
    scheduleOfficeRender(walkUntil - now + 40);
  }

  officeBehaviorState.set(key, {
    position: walkingToDesk ? walkFrom : target,
    status: session.status,
    targetKey,
    walkUntil: walkingToDesk ? walkUntil : 0,
  });

  return {
    activity,
    target,
    walkFrom,
    walkingToDesk,
  };
}

function officeTaskText(session) {
  if (session.status === "idle") {
    return session.project_name || session.progress_summary || session.current_task || session.session_id;
  }
  return session.progress_summary || session.current_task || session.project_name || session.session_id;
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
    token_usage: nextState.token_usage || [],
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
  const emptyOfficeNode = officeView.querySelector("[data-office-empty]");
  if (state.sessions.length === 0) {
    removeStaleOfficeNodes(new Set(), new Set());
    if (!emptyOfficeNode) {
      const empty = emptyNode("No active desks");
      empty.dataset.officeEmpty = "true";
      officeView.append(empty);
    }
    return;
  }
  if (emptyOfficeNode) {
    emptyOfficeNode.remove();
  }

  const machinesById = new Map(state.machines.map((machine) => [machine.machine_id, machine]));
  const sessionsByRuntime = new Map();
  const visibleSessions = state.sessions
    .filter((session) => session.status !== "offline")
    .sort((left, right) => {
      const runtimeCompare = runtimeSortKey(left.runtime_type).localeCompare(runtimeSortKey(right.runtime_type));
      if (runtimeCompare !== 0) {
        return runtimeCompare;
      }
      return sessionKey(left).localeCompare(sessionKey(right));
    });
  visibleSessions.forEach((session) => {
    const runtimeType = session.runtime_type || "other";
    if (!sessionsByRuntime.has(runtimeType)) {
      sessionsByRuntime.set(runtimeType, []);
    }
    sessionsByRuntime.get(runtimeType).push(session);
  });

  const activeRuntimeKeys = new Set();
  const activeDeskKeys = new Set();
  const idlePlans = officeIdlePlans(sessionsByRuntime, Date.now());
  const runtimeSessionIndexes = new Map();
  Array.from(sessionsByRuntime.entries())
    .sort(([left], [right]) => runtimeSortKey(left).localeCompare(runtimeSortKey(right)))
    .forEach(([runtimeType, sessions], runtimeIndex) => {
      activeRuntimeKeys.add(runtimeType);
      const zone = ensureOfficeRuntimeNode(runtimeType);
      updateOfficeRuntimeNode(zone, runtimeType, sessions);
      zone.style.setProperty("--runtime-index", String(runtimeIndex));
      officeView.append(zone);
    });

  visibleSessions.forEach((session) => {
    const runtimeType = session.runtime_type || "other";
    const sessionIndex = runtimeSessionIndexes.get(runtimeType) || 0;
    runtimeSessionIndexes.set(runtimeType, sessionIndex + 1);
    const deskKey = sessionKey(session);
    activeDeskKeys.add(deskKey);
    const desk = ensureOfficeDeskNode(deskKey);
    updateOfficeDeskNode(desk, session, sessionIndex, machinesById.get(session.machine_id), idlePlans);
    officeView.append(desk);
  });

  if (activeRuntimeKeys.size === 0 && !officeView.querySelector("[data-office-empty]")) {
    const empty = emptyNode("No active desks");
    empty.dataset.officeEmpty = "true";
    officeView.append(empty);
  }
  removeStaleOfficeNodes(activeRuntimeKeys, activeDeskKeys);
}

function formatCompactNumber(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) {
    return "0";
  }
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: number >= 1000 ? 1 : 0,
    notation: number >= 10000 ? "compact" : "standard",
  }).format(number);
}

function formatUsageCost(value, unit) {
  const amount = Number(value || 0);
  if (!Number.isFinite(amount)) {
    return unit === "usd" ? "$0.00" : "0";
  }
  if (unit === "usd") {
    return `$${amount.toFixed(amount >= 10 ? 2 : 3)}`;
  }
  if (unit === "credits") {
    return `${amount.toFixed(amount >= 100 ? 1 : 2)} cr`;
  }
  return formatCompactNumber(amount);
}

function usagePeriod(usage, periodName) {
  return (usage.periods || []).find((period) => period.period === periodName) || null;
}

function formatBudget(usage) {
  const week = usagePeriod(usage, "week");
  const budgetSource = week?.budget_amount ? week : usage;
  if (!budgetSource.budget_amount) {
    return "";
  }
  const percent = Math.min(Number(budgetSource.budget_used_ratio || 0) * 100, 999);
  return `${percent.toFixed(percent >= 10 ? 1 : 2)}% / ${formatUsageCost(
    budgetSource.budget_amount,
    budgetSource.billable_unit || usage.billable_unit,
  )}`;
}

function renderUsageModels(usage) {
  const models = [...(usage.model_breakdown || [])]
    .sort((left, right) => Number(right.billable_amount || 0) - Number(left.billable_amount || 0))
    .slice(0, 3);
  if (models.length === 0) {
    return "";
  }
  return `
    <div class="usage-models">
      ${models
        .map(
          (model) => `
            <span>
              <strong>${escapeHtml(model.model || "unknown")}</strong>
              <small>${formatUsageCost(model.billable_amount, model.billable_unit || usage.billable_unit)}</small>
            </span>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderTokenUsage() {
  if (!tokenUsageSummary) {
    return;
  }

  tokenUsageSummary.replaceChildren();
  const usageItems = [...(state.token_usage || [])].sort((left, right) => {
    const runtimeCompare = runtimeSortKey(left.runtime_type).localeCompare(runtimeSortKey(right.runtime_type));
    if (runtimeCompare !== 0) {
      return runtimeCompare;
    }
    return String(left.machine_id || "").localeCompare(String(right.machine_id || ""));
  });
  const totalTokens = usageItems.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0);

  const header = document.createElement("div");
  header.className = "usage-total";
  header.innerHTML = `
    <span>Token usage</span>
    <strong>${formatCompactNumber(totalTokens)}</strong>
  `;
  tokenUsageSummary.append(header);

  if (usageItems.length === 0) {
    tokenUsageSummary.append(emptyNode("No token usage"));
    return;
  }

  const list = document.createElement("div");
  list.className = "usage-breakdown";
  usageItems.forEach((usage) => {
    const item = document.createElement("div");
    item.className = `usage-item runtime-${statusClass(usage.runtime_type || "other")}`;
    const cachedTokens =
      Number(usage.cached_input_tokens || 0) ||
      Number(usage.cache_creation_input_tokens || 0) + Number(usage.cache_read_input_tokens || 0);
    const today = usagePeriod(usage, "today");
    const week = usagePeriod(usage, "week");
    const budget = formatBudget(usage);
    item.innerHTML = `
      <div class="usage-main">
        <span>
          <strong>${escapeHtml(runtimeTypeLabel(usage.runtime_type))}</strong>
          <small>${escapeHtml(usage.machine_id || "-")} / ${escapeHtml(usage.scope || "local_logs")}</small>
        </span>
        <span>${formatUsageCost(usage.billable_amount, usage.billable_unit)}</span>
      </div>
      <div class="usage-periods">
        <span>Total ${formatCompactNumber(usage.total_tokens)} tok</span>
        <span>Today ${formatUsageCost(today?.billable_amount, today?.billable_unit || usage.billable_unit)}</span>
        <span>This week ${formatUsageCost(week?.billable_amount, week?.billable_unit || usage.billable_unit)}</span>
        <span>${formatCompactNumber(cachedTokens)} cached</span>
        ${budget ? `<span>Budget ${escapeHtml(budget)}</span>` : ""}
      </div>
      ${renderUsageModels(usage)}
    `;
    list.append(item);
  });
  tokenUsageSummary.append(list);
}

function runtimeSortKey(runtimeType) {
  const order = RUNTIME_ORDER.indexOf(runtimeType);
  return `${order === -1 ? 99 : order}:${runtimeType}`;
}

function ensureOfficeRuntimeNode(runtimeType) {
  if (officeRuntimeNodes.has(runtimeType)) {
    return officeRuntimeNodes.get(runtimeType);
  }

  const node = document.createElement("article");
  node.className = `office-runtime-zone runtime-zone-${statusClass(runtimeType)}`;
  node.dataset.runtimeType = runtimeType;
  node.innerHTML = `
    <header class="office-zone-header office-stage-label">
      <div>
        <strong data-field="runtime-name"></strong>
        <small data-field="runtime-summary"></small>
      </div>
      <span data-field="runtime-mascot"></span>
    </header>
  `;
  officeRuntimeNodes.set(runtimeType, node);
  return node;
}

function updateOfficeRuntimeNode(node, runtimeType, sessions) {
  const idleCount = sessions.filter((session) => session.status === "idle").length;
  const workingCount = sessions.filter((session) => session.status === "working").length;
  node.querySelector('[data-field="runtime-name"]').textContent = `${runtimeTypeLabel(runtimeType)} Area`;
  node.querySelector('[data-field="runtime-summary"]').textContent =
    `${sessions.length} desks / ${idleCount} idle / ${workingCount} working`;
  const mascot = node.querySelector('[data-field="runtime-mascot"]');
  mascot.className = `runtime-mascot ${mascotForRuntime(runtimeType)}`;
  mascot.textContent = runtimeType === "codex" ? "calf" : runtimeType === "hermes" ? "pony" : "agent";
}

function ensureOfficeDeskNode(deskKey) {
  if (officeDeskNodes.has(deskKey)) {
    return officeDeskNodes.get(deskKey);
  }

  const node = document.createElement("button");
  node.type = "button";
  node.innerHTML = `
    <span class="desk-scene office-asset-scene">
      <span class="generated-agent" data-field="office-agent" aria-hidden="true"></span>
      <span class="generated-desk" aria-hidden="true"></span>
    </span>
    <span class="office-desk-copy">
      <strong data-field="project"></strong>
      <small data-field="runtime"></small>
    </span>
  `;
  node.addEventListener("click", () => {
    selectedSessionId = node.dataset.sessionKey;
    render();
  });
  officeDeskNodes.set(deskKey, node);
  return node;
}

function updateOfficeDeskNode(node, session, sessionIndex, machine, idlePlans) {
  const deskKey = sessionKey(session);
  const status = statusClass(session.status);
  const selected = deskKey === selectedSessionId ? "selected" : "";
  const runtimeClass = `runtime-${statusClass(session.runtime_type || "other")}`;
  const behavior = officeBehaviorForSession(session, sessionIndex, idlePlans, Date.now());
  const activity = behavior.activity;
  const activityClass = `activity-${activity}`;
  const placeClass = `office-place-${behavior.target.place}`;
  const walkingClass = behavior.walkingToDesk ? "walking-to-desk" : "";
  const nextClassName = ["office-desk", runtimeClass, status, activityClass, placeClass, walkingClass, selected]
    .filter(Boolean)
    .join(" ");
  if (node.className !== nextClassName) {
    node.className = nextClassName;
  }
  node.dataset.sessionKey = deskKey;
  node.style.setProperty("--desk-index", String(sessionIndex));
  node.style.setProperty("--actor-x", `${behavior.target.x}%`);
  node.style.setProperty("--actor-y", `${behavior.target.y}%`);
  node.style.setProperty("--walk-from-x", `${behavior.walkFrom.x}%`);
  node.style.setProperty("--walk-from-y", `${behavior.walkFrom.y}%`);
  node.style.setProperty("--actor-z", String(Math.round(behavior.target.y * 10)));

  const person = node.querySelector(".agent-person");
  const mascotClass = mascotForRuntime(session.runtime_type);
  if (person) {
    const personClassName = ["agent-person", mascotClass, status, activityClass].join(" ");
    if (person.className !== personClassName) {
      person.className = personClassName;
    }
  }
  const generatedAgent = node.querySelector('[data-field="office-agent"]');
  const spriteCharacter = officeSpriteCharacter(session.runtime_type);
  const spriteActivity = officeSpriteActivity(session, activity);
  const spriteClassName = [
    "generated-agent",
    `asset-${spriteCharacter}`,
    `asset-${spriteActivity}`,
    status,
    activityClass,
    mascotClass,
  ].join(" ");
  if (generatedAgent && generatedAgent.className !== spriteClassName) {
    generatedAgent.className = spriteClassName;
  }
  node.querySelector('[data-field="project"]').textContent = officeTaskText(session);
  node.querySelector('[data-field="runtime"]').textContent =
    `${runtimeInitial(session.runtime_type)} / ${session.project_name || machine?.hostname || session.machine_id} / ${session.status || "unknown"}`;
}

function removeStaleOfficeNodes(activeRuntimeKeys, activeDeskKeys) {
  for (const [deskKey, node] of officeDeskNodes) {
    if (!activeDeskKeys.has(deskKey)) {
      node.remove();
      officeDeskNodes.delete(deskKey);
      officeBehaviorState.delete(deskKey);
    }
  }
  for (const [runtimeType, node] of officeRuntimeNodes) {
    if (!activeRuntimeKeys.has(runtimeType)) {
      node.remove();
      officeRuntimeNodes.delete(runtimeType);
    }
  }
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
  renderTokenUsage();
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

setInterval(() => {
  if (activeView === "office") {
    renderOffice();
  }
}, OFFICE_BEHAVIOR_SLOT_MS);

setActiveView(activeView);
fetchState().catch((error) => {
  connectionStatus.textContent = error.message;
});
connectWebSocket();
