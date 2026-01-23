from typing import List, Optional, Any, Union, Dict, Literal
from pydantic import BaseModel, Field
from enum import Enum

# ==========================================
# 1. ENUMS (STRICT VALIDATION)
# ==========================================

class IntentCategory(str, Enum):
    RETRIEVAL = "retrieval"
    SUMMARIZATION = "summarization"
    AGGREGATION = "aggregation"
    CHITCHAT = "chitchat"
    ROUTER_KNOWN = "router_known"

class RagIntent(str, Enum):
    RETRIEVAL = "retrieval"
    SUMMARIZATION = "summarization"
    AGGREGATION = "aggregation"

class RelationalLogic(str, Enum):
    DIRECT_MATCH = "direct_match"
    FIRST_UTTERANCE = "first_utterance"
    LAST_UTTERANCE = "last_utterance"
    NEXT_UTTERANCE = "next_utterance"
    PREVIOUS_UTTERANCE = "previous_utterance"

class AggregationType(str, Enum):
    COUNT = "count"
    AVERAGE = "average"
    MIN = "min"
    MAX = "max"
    SUM = "sum"
    
class ScopeMode(str, Enum):
    LATEST_SESSION = "latest_session"
    ALL_SESSIONS = "all_sessions"
    SPECIFIC_SESSIONS = "specific_sessions"

class TargetTable(str, Enum):
    UTTERANCES = "utterances"
    SESSIONS = "sessions"
    CLIENT_INSIGHTS = "client_insights"

class FilterOperator(str, Enum):
    EQ = "eq"
    CONTAINS = "contains"
    ILIKE = "ilike"
    GTE = "gte"
    LTE = "lte"
    IN = "in"

# ==========================================
# 2. SUB-COMPONENT MODELS (UPDATED)
# ==========================================

class RagStrategy(BaseModel):
    """
    Updated to match Prompt Section 4.B -> rag_strategy
    """
    intent: Optional[RagIntent] = None
    relational_logic: Optional[RelationalLogic] = None
    aggregation_type: Optional[AggregationType] = None

class Scope(BaseModel):
    """
    Updated to match Prompt Section 4.B -> scope
    """
    mode: Optional[ScopeMode] = None
    target_session_numbers: List[int] = Field(default_factory=list)

class FilterItem(BaseModel):
    """
    Helper for the individual condition inside the filters list.
    """
    column: str
    operator: FilterOperator
    value: Union[str, int, float, List[str], List[int]]

class Filters(BaseModel):
    """
    Repurposed to match Prompt Section 4.B -> database_query
    (We keep the class name 'Filters' to preserve existing naming conventions,
    but it now represents the full DB Query object).
    """
    target_table: Optional[TargetTable] = None
    filters: List[FilterItem] = Field(default_factory=list)

class Classification(BaseModel):
    is_relevant: bool
    intent_category: IntentCategory

# ==========================================
# 3. EXECUTION ITEM (THE SUB-QUESTION)
# ==========================================

class SubQuestion(BaseModel):
    """
    Represents a single atomic task derived from the execution_plan.
    """
    question_index: int
    original_text: str
    classification: Classification
    direct_response: Optional[str] = None
    
    # These fields map to the prompt's JSON keys.
    # We use the existing class names as types.
    rag_strategy: Optional[RagStrategy] = None
    scope: Optional[Scope] = None
    
    # Map 'database_query' JSON key to the 'Filters' class
    database_query: Optional[Filters] = None 

# ==========================================
# 4. MAIN ROUTER OUTPUT (UPDATED ROOT)
# ==========================================

class QueryOverview(BaseModel):
    number_of_questions: int
    global_relevance: bool
    primary_mood: Optional[str] = "Neutral"

class RouterOutput(BaseModel):
    """
    Updated Root Schema.
    Matches: { "query_overview": ..., "execution_plan": [...] }
    """
    query_overview: QueryOverview
    execution_plan: List[SubQuestion]

# ==========================================
# 5. INPUT/OUTPUT SCHEMAS (UNCHANGED)
# ==========================================

class ChatRequest(BaseModel):
    query: str
    client_id: str
    session_id: Optional[str] = None
    chat_history: List[Dict[str, str]] = []

class Source(BaseModel):
    source_type: str
    session_number: int
    sequence_number: Optional[int] = None
    timestamp: str
    confidence: float

class ChatResponse(BaseModel):
    answer: str
    sources: List[Source] = []
    meta_data: Optional[Dict] = None