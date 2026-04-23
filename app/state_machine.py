"""
Task State Machine for Trading Factory System
Valid transitions:
  PENDING → ASSIGNED → PROCESSING → VALIDATED → COMPLETED
                    ↘ FAILED → ASSIGNED (retry)
"""

from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict, Any


class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    PROCESSING = "processing"
    VALIDATED = "validated"
    COMPLETED = "completed"
    FAILED = "failed"


VALID_TRANSITIONS = {
    TaskStatus.PENDING: [TaskStatus.ASSIGNED],
    TaskStatus.ASSIGNED: [TaskStatus.PROCESSING],
    TaskStatus.PROCESSING: [TaskStatus.VALIDATED, TaskStatus.FAILED],
    TaskStatus.VALIDATED: [TaskStatus.COMPLETED],
    TaskStatus.FAILED: [TaskStatus.ASSIGNED],  # Retry
    TaskStatus.COMPLETED: [],  # Terminal state
}


class StateMachineError(Exception):
    """Raised when an invalid state transition is attempted."""

    pass


class TaskStateMachine:
    """Manages task state transitions with validation and audit logging."""

    def __init__(self, task_id: str, initial_status: TaskStatus = TaskStatus.PENDING):
        self.task_id = task_id
        self.status = initial_status
        self.history: List[Dict[str, Any]] = []
        self.version = 1  # For optimistic locking
        self._record_transition(None, initial_status, "initialized")

    def transition(self, new_status: TaskStatus, changed_by: str, reason: str = "") -> bool:
        """
        Attempt to transition to a new state.

        Returns True if successful, raises StateMachineError if invalid.
        Uses optimistic locking - increments version on each transition.
        """
        if new_status not in VALID_TRANSITIONS[self.status]:
            raise StateMachineError(
                f"Invalid transition: {self.status.value} → {new_status.value}. "
                f"Valid transitions: {[s.value for s in VALID_TRANSITIONS[self.status]]}"
            )

        old_status = self.status
        self.status = new_status
        self.version += 1

        self._record_transition(old_status, new_status, changed_by, reason)
        return True

    def _record_transition(
        self, old_status: Optional[TaskStatus], new_status: TaskStatus, changed_by: str, reason: str = ""
    ):
        """Record state transition in history."""
        self.history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "task_id": self.task_id,
                "old_status": old_status.value if old_status else None,
                "new_status": new_status.value,
                "changed_by": changed_by,
                "reason": reason,
                "version": self.version,
            }
        )

    def can_transition_to(self, status: TaskStatus) -> bool:
        """Check if transition to given status is valid."""
        return status in VALID_TRANSITIONS[self.status]

    def get_valid_transitions(self) -> List[TaskStatus]:
        """Get list of valid next states."""
        return VALID_TRANSITIONS[self.status].copy()

    def get_history(self) -> List[Dict[str, Any]]:
        """Get full transition history."""
        return self.history.copy()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state machine to dict."""
        return {"task_id": self.task_id, "status": self.status.value, "version": self.version, "history": self.history}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskStateMachine":
        """Restore state machine from dict."""
        sm = cls(data["task_id"], TaskStatus(data["status"]))
        sm.version = data.get("version", 1)
        sm.history = data.get("history", [])
        return sm


# Timeout configuration (in hours)
TIMEOUT_CONFIG = {
    TaskStatus.ASSIGNED: 1,  # Must start within 1 hour
    TaskStatus.PROCESSING: 8,  # Max processing time
    TaskStatus.VALIDATED: 1,  # Must complete validation within 1 hour
}


def check_timeout(state_machine: TaskStateMachine) -> Optional[str]:
    """
    Check if current state has exceeded timeout.
    Returns timeout reason if exceeded, None otherwise.
    """
    if state_machine.status not in TIMEOUT_CONFIG:
        return None

    # Get last transition time
    if not state_machine.history:
        return None

    last_transition = state_machine.history[-1]
    last_time = datetime.fromisoformat(last_transition["timestamp"])
    elapsed = (datetime.now() - last_time).total_seconds() / 3600

    timeout_hours = TIMEOUT_CONFIG[state_machine.status]
    if elapsed > timeout_hours:
        return f"Timeout: {state_machine.status.value} exceeded " f"{timeout_hours}h (elapsed: {elapsed:.1f}h)"

    return None


# PostgreSQL optimistic locking query
OPTIMISTIC_LOCK_SQL = """
UPDATE tasks 
SET status = %s, version = version + 1, updated_at = NOW()
WHERE task_id = %s AND version = %s
RETURNING version;
"""
