const TOKEN_KEY = "agentOfficeToken";
const authToken = resolveToken();

let state = { machines: [], sessions: [], agents: [], token_usage: [], commands: [] };
let selectedSessionId = null;
let activeView = "console";
let socket = null;
const officeRuntimeNodes = new Map();
const officeDeskNodes = new Map();
const officeBehaviorState = new Map();
const officeSceneFurnitureNodes = new Map();
const officeSceneDoorNodes = new Map();
const RUNTIME_ORDER = ["codex", "hermes", "claude_code"];
const IDLE_ACTIVITIES = ["sleeping", "phone", "chatting"];
const WAITING_SPRITE_STATUSES = new Set(["waiting_permission", "waiting_input", "blocked", "starting", "waiting"]);
const OFFICE_WALK_MS = 2200;
const OFFICE_BEHAVIOR_SLOT_MS = 60000;
const OFFICE_SCENE_MANIFEST_URL = "/assets/office-scene-v2/scene-manifest.json";
const OFFICE_SCENE_RUNTIME_DESK_IDS = {
  codex: ["desk-01", "desk-02", "desk-03", "desk-04", "desk-05", "desk-06", "desk-07", "desk-08"],
  hermes: ["desk-09", "desk-10", "desk-11", "desk-12"],
  claude_code: ["desk-05", "desk-06", "desk-07", "desk-08"],
};
const OFFICE_SCENE_RUNTIME_LABELS = {
  codex: { x: 1190, y: 84 },
  hermes: { x: 1190, y: 806 },
  claude_code: { x: 520, y: 806 },
  other: { x: 92, y: 84 },
};
let officeRenderTimer = null;
let officeSceneManifest = null;
let officeSceneManifestPromise = null;
let officeSceneBaseNode = null;
const OFFICE_DESK_ANCHORS = {
  codex: [
    { x: 36.8, y: 18.7 },
    { x: 43.4, y: 18.7 },
    { x: 53.2, y: 18.7 },
    { x: 59.3, y: 18.7 },
    { x: 69.0, y: 18.7 },
    { x: 75.2, y: 18.7 },
    { x: 36.6, y: 35.7 },
    { x: 43.5, y: 35.7 },
    { x: 53.1, y: 35.7 },
    { x: 59.6, y: 35.7 },
    { x: 69.5, y: 35.7 },
    { x: 76.2, y: 35.7 },
    { x: 36.2, y: 53.8 },
    { x: 42.8, y: 53.8 },
    { x: 53.2, y: 53.8 },
    { x: 59.8, y: 53.8 },
    { x: 70.2, y: 53.8 },
    { x: 76.5, y: 53.8 },
  ],
  hermes: [
    { x: 88.4, y: 29.0 },
    { x: 93.2, y: 29.0 },
    { x: 88.7, y: 40.1 },
    { x: 93.5, y: 40.1 },
    { x: 89.0, y: 50.9 },
    { x: 93.8, y: 50.9 },
    { x: 68.6, y: 80.0 },
    { x: 73.8, y: 80.0 },
  ],
  claude_code: [
    { x: 26.8, y: 80.0 },
    { x: 31.6, y: 80.0 },
    { x: 22.8, y: 85.0 },
    { x: 31.8, y: 85.0 },
  ],
  other: [
    { x: 36.8, y: 18.7 },
    { x: 53.2, y: 35.7 },
    { x: 70.2, y: 53.8 },
    { x: 88.7, y: 40.1 },
  ],
};
const OFFICE_LOUNGE_ANCHORS = [
  { place: "lounge", label: "沙发区", x: 9.6, y: 55.4 },
  { place: "lounge", label: "讨论区", x: 13.2, y: 78.3 },
  { place: "lounge", label: "会议室", x: 28.5, y: 80.2 },
  { place: "lounge", label: "茶水区", x: 69.2, y: 78.8 },
];

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
  if (idleActivity === "working-back" || session.status === "working") {
    return "working-back";
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

function officeSceneAssetPath(path) {
  return `/assets/office-scene-v2/${path}`;
}

function loadOfficeSceneManifest() {
  if (officeSceneManifest) {
    return Promise.resolve(officeSceneManifest);
  }
  if (officeSceneManifestPromise) {
    return officeSceneManifestPromise;
  }
  officeSceneManifestPromise = fetch(OFFICE_SCENE_MANIFEST_URL, { headers: headers() })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Office scene request failed: ${response.status}`);
      }
      return response.json();
    })
    .then((manifest) => {
      officeSceneManifest = manifest;
      if (activeView === "office") {
        renderOffice();
      }
      return manifest;
    })
    .catch((error) => {
      officeSceneManifestPromise = null;
      connectionStatus.textContent = error.message;
      throw error;
    });
  return officeSceneManifestPromise;
}

function officeSceneDeskEntries(manifest) {
  return (manifest?.furniture || []).filter((item) => item.type === "work-desk");
}

function officeSceneDeskEntriesForRuntime(manifest, runtimeType) {
  const desks = officeSceneDeskEntries(manifest);
  const groupIds = OFFICE_SCENE_RUNTIME_DESK_IDS[runtimeType] || [];
  const grouped = desks.filter((desk) => groupIds.includes(desk.id));
  return grouped.length > 0 ? grouped : desks;
}

function officeSceneFurnitureById(manifest, furnitureId) {
  return (manifest?.furniture || []).find((item) => item.id === furnitureId) || null;
}

function officeSceneWaypoint(manifest, waypointId) {
  return (manifest?.waypoints || []).find((item) => item.id === waypointId) || null;
}

function officeSceneCharacterZIndex(y) {
  return Number(officeSceneManifest?.layering?.characterBase || 1000) + Math.round(Number(y || 0));
}

function officeDeskAnchorForSession(session, sessionIndex) {
  const manifest = officeSceneManifest;
  if (!manifest) {
    return {
      deskId: "fallback-desk",
      front: { x: 960, y: 860, place: "desk", label: "工位" },
      work: { x: 960, y: 820, place: "desk", label: "工位", characterState: "working-back" },
      zIndex: 900,
    };
  }
  const desks = officeSceneDeskEntriesForRuntime(manifest, session.runtime_type || "other");
  const desk = desks[sessionIndex % Math.max(desks.length, 1)] || officeSceneDeskEntries(manifest)[0];
  const front = desk?.anchorPoints?.front || desk?.anchorPoints?.work;
  const work = desk?.anchorPoints?.work || front;
  const wrap = Math.floor(sessionIndex / Math.max(desks.length || 1, 1));
  const wrapX = wrap % 2 === 0 ? 0 : 28;
  const wrapY = Math.floor(wrap / 2) * 20;
  return {
    deskId: desk?.id || "fallback-desk",
    front: {
      x: clamp(Number(front?.x || 960) + wrapX, 120, Number(manifest.canvas?.width || 1920) - 120),
      y: clamp(Number(front?.y || 860) + wrapY, 120, Number(manifest.canvas?.height || 1080) - 36),
      place: "desk",
      label: "工位",
    },
    work: {
      x: clamp(Number(work?.x || 960) + wrapX, 120, Number(manifest.canvas?.width || 1920) - 120),
      y: clamp(Number(work?.y || 820) + wrapY, 120, Number(manifest.canvas?.height || 1080) - 36),
      place: "desk",
      label: "工位",
      characterState: work?.characterState || "working-back",
    },
    zIndex: Number(desk?.zIndex || 900),
  };
}

function officeIdleAnchorForPlan(plan, session, sessionIndex) {
  if (!plan || plan.place === "desk") {
    const desk = officeDeskAnchorForSession(session, sessionIndex);
    return {
      ...desk.front,
      zIndex: officeSceneCharacterZIndex(desk.front.y),
      doorKind: null,
    };
  }
  const manifest = officeSceneManifest;
  if (!manifest) {
    return {
      place: "lounge",
      label: "休息区",
      x: 280,
      y: 835,
      zIndex: officeSceneCharacterZIndex(835),
      doorKind: "lounge",
    };
  }
  const sofa = officeSceneFurnitureById(manifest, "lounge-sofa");
  const meetingTable = officeSceneFurnitureById(manifest, "meeting-table");
  const eastShelf = officeSceneFurnitureById(manifest, "bookshelf-east");
  const breakRoom = officeSceneWaypoint(manifest, "break-room");
  const anchors = [
    {
      place: "lounge",
      label: "休息室",
      x: sofa?.anchorPoints?.rest?.x || 290,
      y: sofa?.anchorPoints?.rest?.y || 835,
      doorKind: "lounge",
    },
    {
      place: "lounge",
      label: "会议桌",
      x: meetingTable?.anchorPoints?.["meet-south"]?.x || 710,
      y: meetingTable?.anchorPoints?.["meet-south"]?.y || 1010,
      doorKind: null,
    },
    {
      place: "lounge",
      label: "茶水间",
      x: breakRoom?.x || 1370,
      y: breakRoom?.y || 850,
      doorKind: null,
    },
    {
      place: "lounge",
      label: "书架",
      x: eastShelf?.anchorPoints?.browse?.x || 1535,
      y: eastShelf?.anchorPoints?.browse?.y || 910,
      doorKind: null,
    },
  ];
  const anchor = anchors[plan.loungeIndex % anchors.length];
  const spread = plan.memberCount > 1 ? plan.memberIndex - (plan.memberCount - 1) / 2 : 0;
  const offsetY = plan.memberCount > 1 ? (plan.memberIndex % 2) * 10 : 0;
  const canvasWidth = Number(manifest.canvas?.width || 1920);
  const canvasHeight = Number(manifest.canvas?.height || 1080);
  const x = clamp(Number(anchor.x) + spread * 62, 90, canvasWidth - 90);
  const y = clamp(Number(anchor.y) + offsetY, 120, canvasHeight - 42);
  return {
    place: anchor.place,
    label: anchor.label,
    x,
    y,
    zIndex: officeSceneCharacterZIndex(y),
    doorKind: anchor.doorKind,
  };
}

function renderOfficeSceneBase(manifest) {
  if (!officeSceneBaseNode) {
    officeSceneBaseNode = document.createElement("div");
    officeSceneBaseNode.className = "office-scene-base";
  }
  officeSceneBaseNode.style.backgroundImage = `url("${officeSceneAssetPath(manifest.assets.background)}")`;
  if (officeSceneBaseNode.parentNode !== officeView) {
    officeView.prepend(officeSceneBaseNode);
  }
}

function renderOfficeSceneFurniture(manifest) {
  for (const item of manifest.furniture || []) {
    let node = officeSceneFurnitureNodes.get(item.id);
    if (!node) {
      node = document.createElement("img");
      node.className = "office-scene-prop";
      node.alt = "";
      node.dataset.sceneId = item.id;
      officeSceneFurnitureNodes.set(item.id, node);
    }
    node.src = officeSceneAssetPath(manifest.assets.furniture[item.asset]);
    node.style.left = `${item.x}px`;
    node.style.top = `${item.y}px`;
    node.style.width = `${item.width}px`;
    node.style.height = `${item.height}px`;
    node.style.zIndex = String(item.zIndex);
    if (node.parentNode !== officeView) {
      officeView.append(node);
    }
  }
}

function renderOfficeSceneDoors(manifest, occupiedDoorKinds = new Set()) {
  for (const door of manifest.doors || []) {
    let node = officeSceneDoorNodes.get(door.id);
    if (!node) {
      node = document.createElement("img");
      node.className = "office-scene-door";
      node.alt = "";
      node.dataset.sceneId = door.id;
      officeSceneDoorNodes.set(door.id, node);
    }
    const nextState = occupiedDoorKinds.has(door.kind) ? "open" : door.state || "closed";
    const nextWidth = nextState === "open" ? door.openWidth : door.closedWidth;
    const nextHeight = nextState === "open" ? door.openHeight : door.closedHeight;
    node.src = officeSceneAssetPath(manifest.assets.doors[door.kind][nextState]);
    node.style.left = `${door.x}px`;
    node.style.top = `${door.y}px`;
    node.style.width = `${nextWidth}px`;
    node.style.height = `${nextHeight}px`;
    node.style.zIndex = String(door.zIndex);
    node.dataset.doorState = nextState;
    if (node.parentNode !== officeView) {
      officeView.append(node);
    }
  }
}

function officeDeskPosition(runtimeType, sessionIndex) {
  const anchors = OFFICE_DESK_ANCHORS[runtimeType] || OFFICE_DESK_ANCHORS.other;
  const anchor = anchors[sessionIndex % anchors.length];
  const wrap = Math.floor(sessionIndex / anchors.length);
  return {
    place: "desk",
    x: clamp(anchor.x + (wrap % 3) * 1.5, 5, 95),
    y: clamp(anchor.y + wrap * 2, 14, 88),
  };
}

function officeLoungePosition(loungeIndex, memberIndex, memberCount) {
  const lounge = OFFICE_LOUNGE_ANCHORS[loungeIndex % OFFICE_LOUNGE_ANCHORS.length];
  const spread = memberCount > 1 ? memberIndex - (memberCount - 1) / 2 : 0;
  return {
    place: lounge.place,
    label: lounge.label,
    x: clamp(lounge.x + spread * 4.2, 5, 95),
    y: clamp(lounge.y + (memberIndex % 2) * 2.8, 14, 88),
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
  const deskAnchor = officeDeskAnchorForSession(session, sessionIndex);
  const key = sessionKey(session);
  const previous = officeBehaviorState.get(key) || {};
  let target = deskAnchor.front;
  let activity = session.status === "working" ? deskAnchor.work.characterState || "working-back" : "stand";
  let actorZIndex = officeSceneCharacterZIndex(target.y);
  if (session.status === "idle") {
    const plan = idlePlans.get(key);
    activity = plan?.activity || idleActivityForSession(session);
    target = officeIdleAnchorForPlan(plan, session, sessionIndex);
    actorZIndex = target.zIndex || officeSceneCharacterZIndex(target.y);
  }

  const walkFrom = previous.position || target;
  const targetKey = `${target.place}:${Math.round(target.x)}:${Math.round(target.y)}:${session.status}`;
  let walkUntil = Number(previous.walkUntil || 0);
  if (session.status === "working") {
    target = deskAnchor.front;
    if (previous.status && previous.status !== "working" && (previous.targetKey !== targetKey || walkUntil <= now)) {
      walkUntil = now + OFFICE_WALK_MS;
    }
  }

  const walkingToDesk = session.status === "working" && walkUntil > now;
  if (walkingToDesk) {
    activity = "walk";
    scheduleOfficeRender(walkUntil - now + 40);
  } else if (session.status === "working") {
    target = deskAnchor.work;
    activity = deskAnchor.work.characterState || "working-back";
    actorZIndex = deskAnchor.zIndex - 1;
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
    actorZIndex: walkingToDesk ? officeSceneCharacterZIndex(target.y) : actorZIndex,
    doorKind: target.doorKind || null,
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
  if (!officeSceneManifest) {
    loadOfficeSceneManifest().catch(() => {});
    const loading = officeView.querySelector("[data-office-empty]");
    if (!loading) {
      const empty = emptyNode("Loading office scene");
      empty.dataset.officeEmpty = "true";
      officeView.append(empty);
    }
    return;
  }
  renderOfficeSceneBase(officeSceneManifest);
  const emptyOfficeNode = officeView.querySelector("[data-office-empty]");
  renderOfficeSceneFurniture(officeSceneManifest);
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
  const occupiedDoorKinds = new Set();
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
    const behavior = updateOfficeDeskNode(desk, session, sessionIndex, machinesById.get(session.machine_id), idlePlans);
    if (behavior?.doorKind) {
      occupiedDoorKinds.add(behavior.doorKind);
    }
    officeView.append(desk);
  });
  renderOfficeSceneDoors(officeSceneManifest, occupiedDoorKinds);

  if (activeDeskKeys.size === 0 && !officeView.querySelector("[data-office-empty]")) {
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
  const position = OFFICE_SCENE_RUNTIME_LABELS[runtimeType] || OFFICE_SCENE_RUNTIME_LABELS.other;
  node.style.setProperty("--runtime-x", `${position.x}px`);
  node.style.setProperty("--runtime-y", `${position.y}px`);
}

function ensureOfficeDeskNode(deskKey) {
  if (officeDeskNodes.has(deskKey)) {
    return officeDeskNodes.get(deskKey);
  }

  const node = document.createElement("button");
  node.type = "button";
  node.innerHTML = `
    <span class="office-actor" aria-hidden="true">
      <span class="generated-agent" data-field="office-agent"></span>
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
  node.style.setProperty("--actor-x", `${behavior.target.x}px`);
  node.style.setProperty("--actor-y", `${behavior.target.y}px`);
  node.style.setProperty("--walk-from-x", `${behavior.walkFrom.x}px`);
  node.style.setProperty("--walk-from-y", `${behavior.walkFrom.y}px`);
  node.style.setProperty("--actor-z", String(behavior.actorZIndex));
  node.style.setProperty("--label-z", String(Number(officeSceneManifest?.layering?.labels || 3000)));

  const mascotClass = mascotForRuntime(session.runtime_type);
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
  node.dataset.doorKind = behavior.doorKind || "";
  return behavior;
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
