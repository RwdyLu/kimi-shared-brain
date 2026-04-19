# PostgreSQL Migration Plan for Trading Factory System

## 1. Current State Analysis

### 1.1 tasks.json Structure
- **Total Tasks**: 107
- **Task States**: completed (94), pending (12), assigned (1)
- **All Fields**: task_id, title, assigned_to, status, priority, type, goal, output_file, deliverables, depends_on, repo_url, report_to, completed_at, reviewed_by, last_updated, estimated_hours

### 1.2 Data Types Mapping
| JSON Field | PostgreSQL Type | Notes |
|------------|-----------------|-------|
| task_id | VARCHAR(50) PRIMARY KEY | e.g., INFRA_001, T-001 |
| title | TEXT | Task description |
| assigned_to | VARCHAR(50) | Agent name |
| status | VARCHAR(20) | assigned/pending/completed/failed |
| priority | VARCHAR(10) | P0/high/medium/low |
| type | VARCHAR(20) | infrastructure/execution/strategy |
| goal | TEXT | Task objective |
| output_file | TEXT | Path to deliverable |
| deliverables | JSONB | Array of deliverable names |
| depends_on | JSONB | Array of task_id dependencies |
| estimated_hours | INTEGER | Estimated completion time |
| completed_at | TIMESTAMP | Completion timestamp |
| reviewed_by | VARCHAR(50) | Reviewer agent |

## 2. PostgreSQL Schema Design

```sql
-- Tasks Table
CREATE TABLE tasks (
    task_id VARCHAR(50) PRIMARY KEY,
    title TEXT NOT NULL,
    assigned_to VARCHAR(50),
    status VARCHAR(20) DEFAULT 'pending',
    priority VARCHAR(10),
    type VARCHAR(20),
    goal TEXT,
    output_file TEXT,
    deliverables JSONB DEFAULT '[]',
    depends_on JSONB DEFAULT '[]',
    estimated_hours INTEGER,
    completed_at TIMESTAMP,
    reviewed_by VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1  -- For optimistic locking
);

-- Task State History (for audit)
CREATE TABLE task_state_history (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(50) REFERENCES tasks(task_id),
    old_status VARCHAR(20),
    new_status VARCHAR(20),
    changed_by VARCHAR(50),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_assigned ON tasks(assigned_to);
CREATE INDEX idx_tasks_priority ON tasks(priority);
```

## 3. Concurrency Control Design

### 3.1 Optimistic Locking
- Use `version` field for optimistic locking
- Increment version on every update
- Check version before update to detect conflicts

```sql
UPDATE tasks 
SET status = 'completed', version = version + 1, completed_at = NOW()
WHERE task_id = 'INFRA_001' AND version = 1;
-- Returns 0 rows if version mismatch (conflict detected)
```

### 3.2 State Machine
Valid transitions:
- pending → assigned
- assigned → processing
- processing → completed
- processing → failed
- failed → assigned (retry)

## 4. Migration Steps

### Step 1: Create PostgreSQL Instance
- Option A: AWS RDS PostgreSQL 14+
- Option B: Alibaba Cloud RDS PostgreSQL 14+
- Minimum: 2 vCPU, 4GB RAM, 20GB storage

### Step 2: Create Tables
Execute schema SQL above

### Step 3: Migrate Data
```python
import json
import psycopg2

# Load JSON
with open('state/tasks.json') as f:
    data = json.load(f)

# Insert to PostgreSQL
for task in data['tasks']:
    # Map JSON to SQL columns
    cur.execute("""
        INSERT INTO tasks (task_id, title, assigned_to, status, priority, type, 
                          goal, output_file, deliverables, depends_on, estimated_hours,
                          completed_at, reviewed_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (task_id) DO UPDATE SET
            title = EXCLUDED.title,
            status = EXCLUDED.status,
            updated_at = NOW()
    """, (task['task_id'], task.get('title'), task.get('assigned_to'),
          task.get('status', 'pending'), task.get('priority'), task.get('type'),
          task.get('goal'), task.get('output_file'), 
          json.dumps(task.get('deliverables', [])),
          json.dumps(task.get('depends_on', [])),
          task.get('estimated_hours'),
          task.get('completed_at'),
          task.get('reviewed_by')))
```

## 5. Connection String Template
```
postgresql://username:password@host:5432/kimi_shared_brain
```

## 6. Testing Plan
1. Unit tests for state machine transitions
2. Concurrency tests with multiple agents
3. Migration validation (count match, data integrity)

---
Generated: 2026-04-20
Author: second_bot (assisting kimiclaw_bot with INFRA_001)
