from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent_office.models import (
    AgentInstance,
    Capability,
    ControlCommand,
    EventRecord,
    EventType,
    Machine,
    ProjectedState,
    RuntimeSession,
    RuntimeType,
    SessionStatus,
    TokenUsageSnapshot,
)


def _capabilities(values: list[str] | None) -> list[Capability]:
    capabilities: list[Capability] = []
    for value in values or []:
        try:
            capabilities.append(Capability(value))
        except ValueError:
            continue
    return capabilities


def _runtime_inventory(values: list[str] | None) -> list[RuntimeType]:
    runtime_inventory: list[RuntimeType] = []
    for value in values or []:
        try:
            runtime_inventory.append(RuntimeType(value))
        except ValueError:
            continue
    return runtime_inventory


def _status(value: object) -> SessionStatus | None:
    if value is None:
        return None
    try:
        return SessionStatus(value)
    except ValueError:
        return None


def _ensure_machine(
    machines: dict[str, Machine],
    event: EventRecord,
) -> Machine:
    machine = machines.get(event.machine_id)
    if machine is None:
        machine = Machine(
            machine_id=event.machine_id,
            hostname=str(event.payload.get("hostname") or event.machine_id),
            last_heartbeat_at=event.timestamp,
            health="online",
        )
        machines[event.machine_id] = machine
    return machine


def _ensure_session(
    sessions: dict[tuple[str, str], RuntimeSession],
    event: EventRecord,
) -> RuntimeSession:
    if event.session_id is None:
        raise ValueError("session_id is required")

    key = (event.machine_id, event.session_id)
    session = sessions.get(key)
    if session is None:
        session = RuntimeSession(
            session_id=event.session_id,
            machine_id=event.machine_id,
            runtime_type=event.runtime_type,
            status=SessionStatus.STARTING,
        )
        sessions[key] = session
    return session


def _update_session_from_event(session: RuntimeSession, event: EventRecord) -> RuntimeSession:
    payload = event.payload
    update: dict[str, object] = {"last_event_at": event.timestamp}

    if event.event_type in (EventType.SESSION_STARTED, EventType.SESSION_UPDATED, EventType.USER_PROMPT):
        if event.event_type == EventType.SESSION_STARTED:
            update["status"] = SessionStatus.WORKING
        else:
            status = _status(payload.get("status"))
            if status is not None:
                update["status"] = status
        for field in ("cwd", "project_name", "model", "current_task", "progress_summary"):
            if field in payload:
                update[field] = payload[field]
        if "capabilities" in payload:
            update["capabilities"] = _capabilities(payload.get("capabilities"))
        if event.source_ref is not None:
            update["source_ref"] = event.source_ref
    elif event.event_type == EventType.TOOL_STARTED:
        update["status"] = SessionStatus.WORKING
        update["progress_summary"] = f"Running tool: {payload.get('tool_name') or 'unknown'}"
    elif event.event_type == EventType.TOOL_FINISHED:
        update["progress_summary"] = f"Finished tool: {payload.get('tool_name') or 'unknown'}"
    elif event.event_type == EventType.WAITING_PERMISSION:
        update["status"] = SessionStatus.WAITING_PERMISSION
        update["progress_summary"] = payload.get("message") or "Waiting for permission"
    elif event.event_type == EventType.SESSION_STOPPED:
        update["status"] = SessionStatus.COMPLETED

    return session.model_copy(update=update)


def _update_agent_from_session(
    agent: AgentInstance,
    session: RuntimeSession,
    event: EventRecord,
) -> AgentInstance:
    payload = event.payload
    update: dict[str, object] = {
        "status": session.status,
        "progress_summary": session.progress_summary,
        "capabilities": session.capabilities,
    }
    if event.event_type == EventType.AGENT_STOPPED:
        update["status"] = SessionStatus.COMPLETED
    if "progress_summary" in payload:
        update["progress_summary"] = payload["progress_summary"]
    field_map = {
        "parent_agent_id": "parent_agent_id",
        "native_agent_id": "native_agent_id",
        "agent_type": "agent_type",
        "task_description": "task_description",
    }
    for payload_field, model_field in field_map.items():
        if payload_field in payload:
            update[model_field] = payload[payload_field]
    return agent.model_copy(update=update)


def _int_payload(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _float_payload(payload: dict[str, object], field: str) -> float:
    value = payload.get(field)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _usage_snapshot_from_event(event: EventRecord) -> TokenUsageSnapshot:
    payload = event.payload
    return TokenUsageSnapshot(
        machine_id=event.machine_id,
        runtime_type=event.runtime_type,
        scope=str(payload.get("scope") or "local_logs"),
        label=str(payload.get("label") or f"{event.runtime_type.value} usage"),
        total_tokens=_int_payload(payload, "total_tokens"),
        input_tokens=_int_payload(payload, "input_tokens"),
        cached_input_tokens=_int_payload(payload, "cached_input_tokens"),
        cache_creation_input_tokens=_int_payload(payload, "cache_creation_input_tokens"),
        cache_creation_5m_input_tokens=_int_payload(payload, "cache_creation_5m_input_tokens"),
        cache_creation_1h_input_tokens=_int_payload(payload, "cache_creation_1h_input_tokens"),
        cache_read_input_tokens=_int_payload(payload, "cache_read_input_tokens"),
        output_tokens=_int_payload(payload, "output_tokens"),
        reasoning_output_tokens=_int_payload(payload, "reasoning_output_tokens"),
        billable_unit=payload.get("billable_unit") if isinstance(payload.get("billable_unit"), str) else None,
        billable_amount=_float_payload(payload, "billable_amount"),
        budget_amount=_float_payload(payload, "budget_amount") if "budget_amount" in payload else None,
        budget_used_ratio=_float_payload(payload, "budget_used_ratio") if "budget_used_ratio" in payload else None,
        request_count=_int_payload(payload, "request_count"),
        session_count=_int_payload(payload, "session_count"),
        updated_at=event.timestamp,
        source_ref=event.source_ref,
        periods=payload.get("periods") if isinstance(payload.get("periods"), list) else [],
        model_breakdown=payload.get("model_breakdown") if isinstance(payload.get("model_breakdown"), list) else [],
    )


def project_state(
    events: list[EventRecord],
    commands: list[ControlCommand],
    now: datetime | None = None,
    heartbeat_timeout: timedelta = timedelta(minutes=5),
) -> ProjectedState:
    now = now or datetime.now(UTC)
    machines: dict[str, Machine] = {}
    sessions: dict[tuple[str, str], RuntimeSession] = {}
    agents: dict[tuple[str, str, str], AgentInstance] = {}
    token_usage: dict[tuple[str, RuntimeType, str], TokenUsageSnapshot] = {}

    for event in sorted(events, key=lambda item: (item.timestamp, item.event_id)):
        if event.event_type == EventType.MACHINE_HEARTBEAT:
            machines[event.machine_id] = Machine(
                machine_id=event.machine_id,
                hostname=str(event.payload.get("hostname") or event.machine_id),
                labels=event.payload.get("labels") or {},
                collector_version=event.payload.get("collector_version"),
                last_heartbeat_at=event.timestamp,
                health="online",
                runtime_inventory=_runtime_inventory(event.payload.get("runtime_inventory")),
            )
        elif event.event_type == EventType.USAGE_SNAPSHOT:
            _ensure_machine(machines, event)
            usage = _usage_snapshot_from_event(event)
            token_usage[(usage.machine_id, usage.runtime_type, usage.scope)] = usage
        else:
            _ensure_machine(machines, event)

        if event.session_id is None:
            continue

        session = _ensure_session(sessions, event)
        session = _update_session_from_event(session, event)
        sessions[(event.machine_id, event.session_id)] = session

        if event.agent_id is not None:
            agent_key = (event.machine_id, event.session_id, event.agent_id)
            agent = agents.get(agent_key)
            if agent is None:
                agent = AgentInstance(
                    agent_id=event.agent_id,
                    machine_id=event.machine_id,
                    session_id=event.session_id,
                )
            agents[agent_key] = _update_agent_from_session(agent, session, event)

    lost_machine_ids: set[str] = set()
    for machine_id, machine in machines.items():
        if machine.last_heartbeat_at is None:
            continue
        if now - machine.last_heartbeat_at > heartbeat_timeout:
            lost_machine_ids.add(machine_id)
            machines[machine_id] = machine.model_copy(update={"health": "lost"})

    for key, session in sessions.items():
        if session.machine_id in lost_machine_ids:
            sessions[key] = session.model_copy(update={"status": SessionStatus.LOST})

    return ProjectedState(
        machines=sorted(machines.values(), key=lambda item: item.machine_id),
        sessions=sorted(sessions.values(), key=lambda item: (item.machine_id, item.session_id)),
        agents=sorted(agents.values(), key=lambda item: (item.machine_id, item.session_id, item.agent_id)),
        token_usage=sorted(
            token_usage.values(),
            key=lambda item: (item.machine_id, item.runtime_type.value, item.scope),
        ),
        commands=sorted(commands, key=lambda item: (item.created_at, item.command_id)),
    )
