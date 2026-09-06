# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
State management service for human-in-the-loop workflow using SQLite.

Provides the same interface as the Firestore-backed implementation,
enabling persistent state tracking, human approval workflows, and resume
capability after human intervention for each loan_request_id.
"""

import json
import os
import sqlite3

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from small_business_loan_agent.shared_libraries.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_DB_PATH = "./mortgage_agent_state.db"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _make_json_serializable(obj: Any) -> Any:
    """Recursively convert datetime objects to ISO format strings."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_serializable(item) for item in obj]
    return obj


class ProcessStateService:
    """Service for managing process states in SQLite."""

    # Step names matching agent names
    STEP_DOCUMENT_EXTRACTION = "DocumentExtractionAgent"
    STEP_UNDERWRITING = "UnderwritingAgent"
    STEP_PRICING = "PricingAgent"
    STEP_LOAN_DECISION = "LoanDecisionAgent"

    ALL_STEPS = (
        STEP_DOCUMENT_EXTRACTION,
        STEP_UNDERWRITING,
        STEP_PRICING,
        STEP_LOAN_DECISION,
    )

    # Status values
    STATUS_NOT_STARTED = "not_started"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_PENDING_APPROVAL = "pending_approval"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_ERROR = "error"

    # Overall process statuses
    OVERALL_STATUS_ACTIVE = "active"
    OVERALL_STATUS_PENDING_APPROVAL = "pending_approval"
    OVERALL_STATUS_COMPLETED = "completed"
    OVERALL_STATUS_FAILED = "failed"

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.getenv("STATE_DB_PATH", DEFAULT_DB_PATH)
        self._ensure_table()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_table(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS process_states (
                    loan_request_id TEXT PRIMARY KEY,
                    state_json      TEXT NOT NULL,
                    updated_at      TEXT NOT NULL
                )
            """)

    def _load(self, conn: sqlite3.Connection, request_id: str) -> dict | None:
        row = conn.execute(
            "SELECT state_json FROM process_states WHERE loan_request_id = ?",
            (request_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["state_json"])

    def _save(self, conn: sqlite3.Connection, request_id: str, state: dict) -> None:
        now = _now_iso()
        state["updated_at"] = now
        conn.execute(
            """
            INSERT INTO process_states (loan_request_id, state_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(loan_request_id) DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (request_id, json.dumps(_make_json_serializable(state)), now),
        )

    def create_process(self, request_id: str, session_id: str) -> dict[str, Any]:
        """Initialize a new process state."""
        now = _now_iso()

        steps = {}
        for step_name in self.ALL_STEPS:
            steps[step_name] = {
                "status": self.STATUS_NOT_STARTED,
                "completed_at": None,
                "data": None,
                "human_review_notes": None,
                "approved_by": None,
                "approved_at": None,
            }

        process_state = {
            "loan_request_id": request_id,
            "session_id": session_id,
            "current_step": self.STEP_DOCUMENT_EXTRACTION,
            "overall_status": self.OVERALL_STATUS_ACTIVE,
            "created_at": now,
            "updated_at": now,
            "steps": steps,
            "issues": [],
        }

        with self._conn() as conn:
            self._save(conn, request_id, process_state)

        logger.info(f"Created process state for request_id: {request_id}")
        return process_state

    def update_step_status(
        self,
        request_id: str,
        step_name: str,
        status: str,
        data: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update the status of a specific step."""
        with self._conn() as conn:
            state = self._load(conn, request_id)
            if state is None:
                logger.error(f"Process state not found for {request_id}")
                return

            step = state["steps"].setdefault(step_name, {})
            step["status"] = status

            if status == self.STATUS_COMPLETED:
                step["completed_at"] = _now_iso()

            if data is not None:
                step["data"] = data

            if error_message:
                step["error_message"] = error_message

            if status == self.STATUS_COMPLETED:
                next_step = self._get_next_step(step_name)
                if next_step:
                    state["current_step"] = next_step

            self._save(conn, request_id, state)

        logger.info(f"Updated step {step_name} to status {status} for request_id: {request_id}")

    def mark_step_for_review(
        self,
        request_id: str,
        step_name: str,
        issue_description: str,
        missing_fields: list[str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Mark a step as requiring human review."""
        with self._conn() as conn:
            state = self._load(conn, request_id)
            if state is None:
                logger.error(f"Process state not found for {request_id}")
                return

            issue: dict[str, Any] = {
                "step": step_name,
                "issue_type": "requires_review",
                "description": issue_description,
                "raised_at": _now_iso(),
                "resolved": False,
                "resolved_at": None,
                "resolved_by": None,
            }
            if missing_fields:
                issue["missing_fields"] = missing_fields

            state["steps"].setdefault(step_name, {})["status"] = self.STATUS_PENDING_APPROVAL
            state["overall_status"] = self.OVERALL_STATUS_PENDING_APPROVAL
            state.setdefault("issues", []).append(issue)

            if data is not None:
                state["steps"][step_name]["data"] = data

            self._save(conn, request_id, state)

        logger.info(f"Marked step {step_name} for review for request_id: {request_id}")

    def can_proceed_to_step(self, request_id: str, step_name: str) -> bool:
        """Check if the process can proceed to a given step."""
        with self._conn() as conn:
            state = self._load(conn, request_id)

        if state is None:
            return False

        steps = state.get("steps", {})

        try:
            step_index = self.ALL_STEPS.index(step_name)
        except ValueError:
            return False

        for i in range(step_index):
            prev_step_name = self.ALL_STEPS[i]
            prev_status = steps.get(prev_step_name, {}).get("status")
            if prev_status not in [self.STATUS_COMPLETED, self.STATUS_APPROVED]:
                return False

        return True

    def get_process_status(self, request_id: str) -> dict[str, Any] | None:
        """Get the current status of a process."""
        with self._conn() as conn:
            return self._load(conn, request_id)

    def mark_process_complete(self, request_id: str) -> None:
        """Mark the entire process as complete."""
        with self._conn() as conn:
            state = self._load(conn, request_id)
            if state is None:
                logger.error(f"Process state not found for {request_id}")
                return
            state["current_step"] = None
            state["overall_status"] = self.OVERALL_STATUS_COMPLETED
            state["completed_at"] = _now_iso()
            self._save(conn, request_id, state)

        logger.info(f"Marked process complete for request_id: {request_id}")

    def _get_next_step(self, current_step: str) -> str | None:
        """Get the next step in the workflow."""
        try:
            current_index = self.ALL_STEPS.index(current_step)
            if current_index < len(self.ALL_STEPS) - 1:
                return self.ALL_STEPS[current_index + 1]
            return None
        except ValueError:
            return None
