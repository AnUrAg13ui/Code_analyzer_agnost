import asyncio
import sys
import os

# Ensure the root directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.deepseek_local_client import get_llm_client
from config.prompts.bug_detector import SYSTEM_PROMPT, FINDING_SCHEMA

async def test_bug_detection():
    llm = get_llm_client()

    # Test if health check passes
    health = await llm.health_check()
    print(f"LLM Health Check: {health}")

    if not health:
        print("LLM is not reachable. Please start the model server.")
        return

    # Read the bug context
    with open("bug_context.txt", "r", encoding="utf-8") as f:
        content = f.read()

    # Extract the bug detector fragment (simplified)
    # For testing, we'll use a portion of the content
    test_context = """
## File: main.py
Status: modified | +4 / -4 lines

### Diff Patch
```diff
@@ -21,21 +21,21 @@ def read_root():
 # Get all tasks
 @app.get("/tasks")
 def get_tasks():
-    return tasks
+    return task

 # Get task by id
 @app.get("/tasks/{task_id}")
 def get_task(task_id: int):
     for task in tasks:
         if task.id == task_id:
             return task
-    raise HTTPException(status_code=404, detail="Task not found")
+    raise HTTPException(status_code=400, detail="Task not found")

 # Create task
 @app.post("/tasks")
 def create_task(task: Task):
     tasks.append(task)
-    return {"message": "Task created", "task": task}
+    return {"message": "Task created", "task": task.idd}

 # Update task
 @app.put("/tasks/{task_id}")
 def update_task(task_id: int, updated_task: Task):
     for index, task in enumerate(tasks):
         if task.id == task_id:
             tasks[index] = updated_task
             return {"message": "Task updated"}
     raise HTTPException(status_code=404, detail="Task not found")

 # Delete task
 @app.delete("/tasks/{task_id}")
 def delete_task(task_id: int):
     for task in tasks:
-        if task.id == task_id:
+        if task.id = task_id:
             tasks.remove(task)
             return {"message": "Task deleted"}
     raise HTTPException(status_code=404, detail="Task not found")
```

### Full File Content (Current State)
```
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

app = FastAPI()

# Data Model
class Task(BaseModel):
    id: int
    title: str
    description: str
    completed: bool = False

tasks: List[Task] = []

# Root API
@app.get("/")
def read_root():
    return {"message": "Welcome to FastAPI Task Manager"}

# Get all tasks
@app.get("/tasks")
def get_tasks():
    return task

# Get task by id
@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=400, detail="Task not found")

# Create task
@app.post("/tasks")
def create_task(task: Task):
    tasks.append(task)
    return {"message": "Task created", "task": task.idd}

# Update task
@app.put("/tasks/{task_id}")
def update_task(task_id: int, updated_task: Task):
    for index, task in enumerate(tasks):
        if task.id == task_id:
            tasks[index] = updated_task
            return {"message": "Task updated"}
    raise HTTPException(status_code=404, detail="Task not found")

# Delete task
@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    for task in tasks:
        if task.id = task_id:
            tasks.remove(task)
            return {"message": "Task deleted"}
    raise HTTPException(status_code=404, detail="Task not found")
```

### AST Structure Signal
AST parse error: cannot assign to attribute here. Maybe you meant '==' instead of '='? (<unknown>, line 53)
"""

    prompt = f"""
Analyze the following code changes for bugs, vulnerabilities, and unsafe patterns.

SPECIFICALLY LOOK FOR:
- Syntax errors and compilation issues
- Runtime errors (NameError, AttributeError, etc.)
- Logic errors in the code
- Incorrect variable names or attribute access
- Wrong operators (= instead of ==)
- HTTP status code misuse

For each bug found, provide:
- The exact line of code with the problem
- What the error is specifically
- Why it's wrong
- The correct fix

{test_context}

{FINDING_SCHEMA}
""".strip()

    print("Sending prompt to LLM...")
    result = await llm.generate_structured(prompt, SYSTEM_PROMPT)
    print("LLM Response:")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_bug_detection())