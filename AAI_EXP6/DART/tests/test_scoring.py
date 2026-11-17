from dart.evaluation.scoring import calculate_run_metrics, selection_scores, regression_detection_rate

def test_reduction_metric():
    result = calculate_run_metrics(10, 4, {"status": "passed", "duration_seconds": 2, "passed": 5}, 3)
    assert result["test_reduction_pct"] == 60.0

def test_selection_scores():
    result = selection_scores({"a", "b"}, {"b", "c"})
    assert result["selection_precision"] == 0.5
    assert result["selection_recall"] == 0.5

def test_detection_rate():
    result = regression_detection_rate({"fault1"}, {"fault1", "fault2"})
    assert result["regression_detection_rate"] == 0.5
