"""State definition for FK Inferencing Agent."""

from typing import TypedDict, List, Dict, Tuple, Optional, Literal


class FKInferencingState(TypedDict):
    """State for the FK inferencing workflow."""

    # Configuration
    database_name: str
    threshold: float
    top_k: int
    excel_path: str
    skip_primary_keys: bool  # Auto-skip columns that are primary keys

    # Schema data
    schema: List[Dict]
    # Note: vector_store is passed via context, not stored in state (not serializable)

    # Current row processing
    current_row_idx: Optional[int]
    current_table: str
    current_column: str
    current_base_name: str
    current_is_pk: bool  # Is the current column a primary key

    # Candidates
    candidates: List[Tuple[str, float]]  # (table_name, score)
    score_gap: float

    # Decision
    chosen_table: Optional[str]
    chosen_score: Optional[float]
    decision_type: Optional[Literal["auto", "manual", "existing", "skipped"]]
    notes: str

    # Flow control
    has_next_row: bool
    user_quit: bool

    # Statistics
    total_rows: int
    processed_count: int

    # Debugging
    last_step: str
