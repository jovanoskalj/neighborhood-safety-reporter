import pytest
from django.db import connection


EXPECTED_INDEXES = [
    ("report_status_idx",           ["status"]),
    ("report_sector_idx",           ["sector"]),
    ("report_category_idx",         ["category"]),
    ("report_municipality_idx",     ["municipality"]),
    ("report_priority_idx",         ["priority"]),
    ("report_latitude_idx",         ["latitude"]),
    ("report_longitude_idx",        ["longitude"]),
    ("report_sector_status_idx",    ["sector", "status"]),
    ("report_is_duplicate_idx",     ["is_duplicate"]),
]

TABLE_NAME = "reports_report"


def get_db_constraints():
    with connection.cursor() as cursor:
        return connection.introspection.get_constraints(cursor, TABLE_NAME)


@pytest.mark.django_db
def test_report_table_exists():
    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
    assert TABLE_NAME in tables, (
        f"Table '{TABLE_NAME}' not found. Run migrations first."
    )


@pytest.mark.django_db
def test_all_expected_indexes_exist():
    constraints = get_db_constraints()
    db_index_names = {
        name for name, info in constraints.items() if info.get("index")
    }

    missing = [
        idx_name for idx_name, _ in EXPECTED_INDEXES
        if idx_name not in db_index_names
    ]

    assert not missing, (
        f"Missing indexes in '{TABLE_NAME}': {missing}\n"
        f"Indexes found in DB: {sorted(db_index_names)}"
    )


@pytest.mark.django_db
def test_index_columns_match():
    constraints = get_db_constraints()

    mismatches = []
    for idx_name, expected_cols in EXPECTED_INDEXES:
        if idx_name not in constraints:
            mismatches.append(f"{idx_name}: NOT FOUND in DB")
            continue
        actual_cols = constraints[idx_name].get("columns", [])
        if actual_cols != expected_cols:
            mismatches.append(
                f"{idx_name}: expected columns {expected_cols}, got {actual_cols}"
            )

    assert not mismatches, "Index column mismatches:\n" + "\n".join(mismatches)


@pytest.mark.django_db
def test_spatial_indexes_exist():
    constraints = get_db_constraints()
    indexed_cols = {
        col
        for info in constraints.values()
        if info.get("index")
        for col in info.get("columns", [])
    }

    for col in ("latitude", "longitude"):
        assert col in indexed_cols, (
            f"Column '{col}' is not indexed on '{TABLE_NAME}'. "
            "Map bounding-box queries will be slow without it."
        )


@pytest.mark.django_db
def test_composite_sector_status_index_exists():
    """The composite (sector, status) index must exist for officer panel queries."""
    constraints = get_db_constraints()
    assert "report_sector_status_idx" in constraints, (
        "Composite index 'report_sector_status_idx' not found. "
        "Add it in Report.Meta.indexes."
    )
    cols = constraints["report_sector_status_idx"].get("columns", [])
    assert cols == ["sector", "status"], (
        f"Expected ['sector', 'status'], got {cols}"
    )
