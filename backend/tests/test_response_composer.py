from datetime import date

from app.services.response_composer import ResponseType, compose


def test_single_scalar_result_is_text():
    result = compose("single_value", ["total"], [[42]])
    assert result.response_type == ResponseType.TEXT
    assert result.chart is None
    assert result.table is None


def test_empty_result_is_text():
    result = compose("lookup", ["a", "b"], [])
    assert result.response_type == ResponseType.TEXT


def test_trend_with_date_and_numeric_column_is_line_chart():
    rows = [[date(2024, 1, 1), 100.0], [date(2024, 2, 1), 150.0]]
    result = compose("trend", ["month", "revenue"], rows)
    assert result.response_type == ResponseType.LINE
    assert result.chart is not None
    assert result.chart.type == "chart:line"
    assert [p.x for p in result.chart.data] == ["2024-01-01", "2024-02-01"]
    assert result.chart.data[0].series[0].name == "revenue"
    assert result.chart.data[0].series[0].value == 100.0


def test_comparison_with_category_and_numeric_column_is_bar_chart():
    rows = [["Electronics", 482000.0], ["Home & Kitchen", 310000.0], ["Toys", 90000.0]]
    result = compose("comparison", ["category", "revenue"], rows)
    assert result.response_type == ResponseType.BAR
    assert result.chart.type == "chart:bar"


def test_distribution_with_few_categories_is_pie_chart():
    rows = [["A", 10.0], ["B", 20.0], ["C", 30.0]]
    result = compose("distribution", ["category", "count"], rows)
    assert result.response_type == ResponseType.PIE
    assert result.chart.type == "chart:pie"


def test_distribution_with_many_categories_falls_back_to_bar():
    rows = [[f"cat{i}", float(i)] for i in range(10)]
    result = compose("distribution", ["category", "count"], rows)
    assert result.response_type == ResponseType.BAR


def test_lookup_intent_is_table():
    rows = [["a", 1, "x"], ["b", 2, "y"]]
    result = compose("lookup", ["name", "count", "tag"], rows)
    assert result.response_type == ResponseType.TABLE
    assert result.table.columns == ["name", "count", "tag"]
    assert result.table.rows == rows


def test_trend_intent_without_date_column_falls_back_to_table():
    rows = [["a", 1], ["b", 2]]
    result = compose("trend", ["name", "count"], rows)
    assert result.response_type == ResponseType.TABLE


def test_too_many_categories_falls_back_to_table():
    rows = [[f"cat{i}", float(i)] for i in range(60)]
    result = compose("comparison", ["category", "value"], rows)
    assert result.response_type == ResponseType.TABLE
