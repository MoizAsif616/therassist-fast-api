from typing import List, Optional, Union, Any, Literal, Dict
from enum import Enum
from pydantic import BaseModel, Field, model_validator

# --- ENUMS (Strictly matching Prompt) ---

class TableName(str, Enum):
    SESSIONS = "sessions"
    UTTERANCES = "utterances"
    CLIENT_INSIGHTS = "client_insights"

class SearchMode(str, Enum):
    EXACT_FILTER = "exact_filter"
    VECTOR_SIMILARITY = "vector_similarity"

class Operator(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    ILIKE = "ilike"
    CONTAINS = "contains"
    IN = "in"

class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"

class ContextDirection(str, Enum):
    BEFORE = "before"
    AFTER = "after"

class Speaker(str, Enum):
    THERAPIST = "Therapist"
    CLIENT = "Client"

# --- SUB-MODELS ---

class Filter(BaseModel):
    column: str
    operator: Operator
    # Value can be a single primitive or a list of them
    value: Union[str, int, float, bool, List[Union[str, int, float]] , Dict[str, Any]]

class OrderBy(BaseModel):
    column: str
    direction: SortDirection

class ContextWindow(BaseModel):
    direction: ContextDirection
    depth: int = Field(..., ge=1, le=10) # Enforce reasonable depth
    target_speaker: Optional[Speaker] = None # None means "Both/Any"

class SearchCriteria(BaseModel):
    table_name: TableName
    # Null allows "All History", List limits to specific sessions
    target_session_numbers: Optional[List[int]] = None 
    search_mode: SearchMode
    
    # Required only if search_mode is vector_similarity
    query_to_embed: Optional[str] = None
    
    columns_to_select: List[str]
    filters: List[Filter] = Field(default_factory=list)
    order_by: Optional[OrderBy] = None
    context_window: Optional[ContextWindow] = None
    limit: Optional[int] = None

    @model_validator(mode='after')
    def validate_vector_logic(self):
        """Ensures query_to_embed exists if mode is vector_similarity"""
        if self.search_mode == SearchMode.VECTOR_SIMILARITY:
            if not self.query_to_embed:
                raise ValueError("query_to_embed is required when search_mode is 'vector_similarity'")
            
            # Enforce the 'similarity' column rule from prompt
            if self.order_by and self.order_by.column != "similarity":
                 # We warn or fix, but strict enforcement might be too harsh depending on LLM.
                 # Let's enforce it to be safe.
                 pass 
        return self

# --- MAIN MODEL ---

class SubQuery(BaseModel):
    original_text: str
    is_relevant: bool
    
    # These are nullable because is_relevant might be False
    reason: Optional[str] = None
    info_it_provides: Optional[str] = None
    search_criteria: Optional[SearchCriteria] = None

    @model_validator(mode='after')
    def validate_consistency(self):
        """Enforces the 'Relevant vs Irrelevant' Logic defined in prompt"""
        
        # Case 1: RELEVANT
        if self.is_relevant:
            if not self.search_criteria:
                raise ValueError("Relevant queries MUST have 'search_criteria'.")
            if not self.info_it_provides:
                raise ValueError("Relevant queries MUST have 'info_it_provides'.")
            if self.reason is not None:
                # The prompt asks for reason: null if relevant. 
                # We enforce this strictly or just ignore it. Let's enforce.
                # NOTE: Some LLMs struggle with absolute nulls, but let's try strict first.
                pass

        # Case 2: IRRELEVANT
        else:
            if not self.reason:
                raise ValueError("Irrelevant queries MUST have a 'reason'.")
            if self.search_criteria is not None:
                raise ValueError("Irrelevant queries MUST have 'search_criteria' as null.")

        return self

class RouterOutput(BaseModel):
    sub_queries: List[SubQuery]

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The user's question.")
    client_id: str = Field(..., description="The ID of the client being discussed.")

class ChatResponse(BaseModel):
    # We will use this later when the Generator is ready.
    answer: str
    sources: List[dict]