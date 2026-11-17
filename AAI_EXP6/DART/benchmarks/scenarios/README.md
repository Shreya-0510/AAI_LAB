Add one JSON file per controlled scenario. Suggested schema:

```json
{
  "scenario_id": "calc-001",
  "repository": "path-or-url",
  "base_commit": "full-sha",
  "head_commit": "full-sha",
  "changed_files": ["src/calculator.py"],
  "expected_relevant_tests": ["tests/test_calculator.py"],
  "injected_fault_id": "fault-001",
  "expected_detection_tests": ["tests/test_percentage.py"]
}
```

Do not use an empty or guessed expected-test list as ground truth. Have a reviewer curate and document it.
