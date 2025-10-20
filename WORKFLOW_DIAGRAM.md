# Conversational Flow Workflow Diagram

## Complete Workflow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              START                                       │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  is_continuation?    │
                    └──────────┬───────────┘
                               │
                ┌──────────────┴──────────────┐
                │                             │
          [False] New Query            [True] Follow-up
                │                             │
                ▼                             ▼
    ┌───────────────────────┐    ┌────────────────────────┐
    │  analyze_schema       │    │  conversational_router │
    │  (Retrieve full       │    │  (Analyze context &    │
    │   schema)             │    │   decide routing)      │
    └───────────┬───────────┘    └────────────┬───────────┘
                │                             │
                │              ┌──────────────┴──────────────┐
                │              │                             │
                │      [revise_query_inline]      [update_plan OR rewrite_plan]
                │              │                             │
                │              │                             ▼
                │              │                  ┌──────────────────────┐
                │              │                  │  planner             │
                │              │                  │  (Mode: update or    │
                │              │                  │   rewrite)           │
                │              │                  └──────────┬───────────┘
                │              │                             │
                ▼              │                             ▼
    ┌───────────────────────┐  │              ┌──────────────────────┐
    │  planner              │  │              │  generate_query      │
    │  (Mode: initial)      │  │              │  (Convert plan       │
    └───────────┬───────────┘  │              │   to SQL)            │
                │              │              └──────────┬───────────┘
                ▼              │                         │
    ┌───────────────────────┐  │                         │
    │  generate_query       │  │                         │
    │  (Convert plan        │  │                         │
    │   to SQL)             │  │                         │
    └───────────┬───────────┘  │                         │
                │              │                         │
                └──────────────┴─────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  execute_query       │
                    │  (Run SQL & store    │
                    │   in queries list)   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Error or empty?     │
                    └──────────┬───────────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
        [Error]          [Empty Result]        [Success]
            │                  │                  │
            ▼                  ▼                  ▼
    ┌───────────────┐  ┌──────────────┐  ┌─────────────┐
    │ handle_error  │  │ refine_query │  │  cleanup    │
    │ (Fix SQL)     │  │ (Improve)    │  │             │
    └───────┬───────┘  └──────┬───────┘  └─────┬───────┘
            │                  │                │
            └──────────────────┴────────┐       │
                                        │       │
                                        ▼       │
                            ┌──────────────┐    │
                            │ execute_query│    │
                            └──────┬───────┘    │
                                   │            │
                                   └────────────┘
                                                │
                                                ▼
                                             ┌─────┐
                                             │ END │
                                             └─────┘
```

## Router Decision Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                  conversational_router                          │
│                                                                 │
│  Inputs:                                                        │
│  - user_questions (conversation history)                        │
│  - queries (SQL history)                                        │
│  - planner_outputs (plan history)                               │
│  - schema (filtered from previous run)                          │
│  - latest user request                                          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │  Analyze Request Type  │
                  └────────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
    ┌─────────────────┐ ┌─────────────┐ ┌──────────────┐
    │ Small SQL       │ │ Minor Plan  │ │ Major Change │
    │ Change          │ │ Change      │ │              │
    │                 │ │             │ │              │
    │ Examples:       │ │ Examples:   │ │ Examples:    │
    │ - Add column    │ │ - Add filter│ │ - Different  │
    │ - Remove column │ │ - Change    │ │   tables     │
    │ - Change LIMIT  │ │   grouping  │ │ - New domain │
    └────────┬────────┘ └──────┬──────┘ └──────┬───────┘
             │                 │                │
             ▼                 ▼                ▼
    ┌─────────────────┐ ┌─────────────┐ ┌──────────────┐
    │ revise_query_   │ │ update_plan │ │ rewrite_plan │
    │ inline          │ │             │ │              │
    │                 │ │             │ │              │
    │ Sets:           │ │ Sets:       │ │ Sets:        │
    │ - query (SQL)   │ │ - router_   │ │ - router_    │
    │ - router_mode   │ │   mode:     │ │   mode:      │
    │   = None        │ │   "update"  │ │   "rewrite"  │
    │                 │ │ - router_   │ │ - router_    │
    │ Goes to:        │ │   instruc-  │ │   instruc-   │
    │ execute_query   │ │   tions     │ │   tions      │
    │                 │ │             │ │              │
    │                 │ │ Goes to:    │ │ Goes to:     │
    │                 │ │ planner     │ │ planner      │
    └─────────────────┘ └─────────────┘ └──────────────┘
```

## Planner Mode Comparison

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          PLANNER NODE                                   │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┬──────────────────────┬──────────────────────────┐
│   Initial Mode       │    Update Mode       │    Rewrite Mode          │
│   (router_mode=None) │  (router_mode=       │  (router_mode=           │
│                      │   "update")          │   "rewrite")             │
├──────────────────────┼──────────────────────┼──────────────────────────┤
│                      │                      │                          │
│ Context:             │ Context:             │ Context:                 │
│ ✓ Full schema        │ ✓ Previous plan      │ ✓ Full schema            │
│ ✓ User query         │ ✓ Router instruc-    │ ✓ Previous plan          │
│ ✓ Query params       │     tions            │     (for context)        │
│                      │ ✓ Conversation       │ ✓ Router instruc-        │
│                      │     history          │     tions                │
│                      │ ✗ Full schema        │ ✓ Conversation           │
│                      │     (omitted)        │     history              │
│                      │                      │                          │
│ Task:                │ Task:                │ Task:                    │
│ Create new plan      │ Update existing      │ Create new plan          │
│ from scratch         │ plan incrementally   │ for new request          │
│                      │                      │                          │
│ When:                │ When:                │ When:                    │
│ First query in       │ Minor modifications  │ Major changes            │
│ conversation         │ (filters, columns)   │ (different tables)       │
│                      │                      │                          │
│ Prompt:              │ Prompt:              │ Prompt:                  │
│ "Analyze schema      │ "Update the plan     │ "Create fresh plan       │
│  and create plan"    │  based on instruc-   │  for new request"        │
│                      │  tions"              │                          │
│                      │                      │                          │
│ Output:              │ Output:              │ Output:                  │
│ New PlannerOutput    │ Modified Planner-    │ New PlannerOutput        │
│                      │ Output               │                          │
│                      │                      │                          │
│ Appends to:          │ Appends to:          │ Appends to:              │
│ planner_outputs[0]   │ planner_outputs[n]   │ planner_outputs[n]       │
└──────────────────────┴──────────────────────┴──────────────────────────┘
```

## State Evolution Through Conversation

```
Initial Query:
┌────────────────────────────────────────────────────────────┐
│ is_continuation: False                                     │
│ user_questions: ["Show me companies"]                      │
│ queries: []                                                │
│ planner_outputs: []                                        │
│ router_mode: None                                          │
└────────────────────────────────────────────────────────────┘
                              │
                              ▼ (workflow executes)
┌────────────────────────────────────────────────────────────┐
│ is_continuation: False                                     │
│ user_questions: ["Show me companies"]                      │
│ queries: ["SELECT * FROM Companies"]                       │
│ planner_outputs: [{...plan1...}]                           │
│ result: "[{...data...}]"                                   │
└────────────────────────────────────────────────────────────┘

Follow-up Query (passed as previous_state):
┌────────────────────────────────────────────────────────────┐
│ is_continuation: True  ← SET                               │
│ user_questions: ["Show me companies",                      │
│                  "Add vendor column"]  ← APPENDED          │
│ queries: ["SELECT * FROM Companies"]   ← CARRIED OVER      │
│ planner_outputs: [{...plan1...}]       ← CARRIED OVER      │
│ router_mode: None                      ← RESET             │
└────────────────────────────────────────────────────────────┘
                              │
                              ▼ (router decides)
┌────────────────────────────────────────────────────────────┐
│ router_mode: None (inline revision)   ← SET BY ROUTER      │
│ query: "SELECT *, Vendor FROM Companies" ← SET BY ROUTER   │
└────────────────────────────────────────────────────────────┘
                              │
                              ▼ (execute_query runs)
┌────────────────────────────────────────────────────────────┐
│ queries: ["SELECT * FROM Companies",                       │
│           "SELECT *, Vendor FROM Companies"] ← APPENDED    │
│ result: "[{...new data...}]"                               │
└────────────────────────────────────────────────────────────┘

Third Query:
┌────────────────────────────────────────────────────────────┐
│ is_continuation: True                                      │
│ user_questions: ["Show me companies",                      │
│                  "Add vendor column",                      │
│                  "Only active companies"]  ← APPENDED      │
│ queries: ["SELECT * FROM Companies",                       │
│           "SELECT *, Vendor FROM Companies"]               │
│ planner_outputs: [{...plan1...}]                           │
│ router_mode: None                                          │
└────────────────────────────────────────────────────────────┘
                              │
                              ▼ (router decides)
┌────────────────────────────────────────────────────────────┐
│ router_mode: "update"                  ← SET BY ROUTER     │
│ router_instructions: "Add filter       ← SET BY ROUTER     │
│    Status = 'Active'"                                      │
└────────────────────────────────────────────────────────────┘
                              │
                              ▼ (planner runs in update mode)
┌────────────────────────────────────────────────────────────┐
│ planner_outputs: [{...plan1...},                           │
│                   {...plan2...}]       ← APPENDED          │
└────────────────────────────────────────────────────────────┘
                              │
                              ▼ (generate_query & execute)
┌────────────────────────────────────────────────────────────┐
│ queries: ["SELECT * FROM Companies",                       │
│           "SELECT *, Vendor FROM Companies",               │
│           "SELECT *, Vendor FROM Companies                 │
│            WHERE Status = 'Active'"]   ← APPENDED          │
│ result: "[{...filtered data...}]"                          │
└────────────────────────────────────────────────────────────┘
```

## Key Decision Points

### 1. Initial Routing (START)
```
if is_continuation == False:
    → analyze_schema (new conversation)
else:
    → conversational_router (follow-up)
```

### 2. Router Routing
```
if router_mode in ["update", "rewrite"]:
    → planner (need to modify plan)
else:  # inline revision
    → execute_query (query already set)
```

### 3. Execute Query Routing
```
if "Error" in message and retry_count < max:
    → handle_error
elif result is None and refined_count < max:
    → refine_query
else:
    → cleanup
```

## Data Flow Summary

```
User Input → query_database()
                │
                ├─ New: is_continuation=False
                │   └─→ analyze_schema → planner(initial) → generate_query
                │                                               │
                └─ Follow-up: is_continuation=True              │
                    └─→ conversational_router                   │
                         ├─ inline → (query set)               │
                         └─ update/rewrite → planner(mode)     │
                                              │                 │
                                              └─→ generate_query
                                                       │
                                                       ▼
                                                  execute_query
                                                       │
                                                       ├─ Success → cleanup → END
                                                       ├─ Error → handle_error → execute_query
                                                       └─ Empty → refine_query → execute_query
```
