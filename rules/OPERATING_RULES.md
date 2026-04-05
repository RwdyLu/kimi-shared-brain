# Operating Rules

1. Kimi A is the only scheduler and final reporter.
2. Kimi A is the only agent allowed to update state/tasks.json.
3. Kimi B must read rules before starting any task.
4. Kimi B must not directly report final completion to the user.
5. Kimi B writes results to outbox/ and outputs/ only.
6. Setup complete does not mean running.
7. If blocked, write blocker details to outbox and stop.
