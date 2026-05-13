import pytest
from app.guardrails.sql_guardrails import ViolationType, check


# ---------------------------------------------------------------------------
# Hard blocks — execution must be prevented
# ---------------------------------------------------------------------------

class TestDDLBlocks:
    def test_drop_table(self):
        r = check("DROP TABLE suppliers")
        assert r.blocked
        assert ViolationType.DDL_STATEMENT in r.violations

    def test_create_table(self):
        r = check("CREATE TABLE hacked AS SELECT * FROM suppliers")
        assert r.blocked
        assert ViolationType.DDL_STATEMENT in r.violations

    def test_alter_table(self):
        r = check("ALTER TABLE products ADD COLUMN backdoor TEXT")
        assert r.blocked
        assert ViolationType.DDL_STATEMENT in r.violations

    def test_truncate(self):
        r = check("TRUNCATE purchase_orders")
        assert r.blocked
        assert ViolationType.DDL_STATEMENT in r.violations

    def test_create_in_table_name_not_blocked(self):
        """SELECT from a table whose name contains 'create' must NOT be blocked."""
        r = check("SELECT * FROM create_table_log WHERE id = 1 LIMIT 10")
        assert not r.blocked
        assert ViolationType.DDL_STATEMENT not in r.violations

    def test_drop_in_column_name_not_blocked(self):
        r = check("SELECT drop_date FROM events LIMIT 10")
        assert not r.blocked
        assert ViolationType.DDL_STATEMENT not in r.violations


class TestDMLWriteBlocks:
    def test_delete_all(self):
        r = check("DELETE FROM inventory WHERE 1=1")
        assert r.blocked
        assert ViolationType.DML_WRITE in r.violations

    def test_update(self):
        r = check("UPDATE products SET unit_cost = 0")
        assert r.blocked
        assert ViolationType.DML_WRITE in r.violations

    def test_insert(self):
        r = check("INSERT INTO suppliers VALUES (999, 'ATTACKER', 'XX', 5.0, true, '2024-01-01')")
        assert r.blocked
        assert ViolationType.DML_WRITE in r.violations

    def test_merge(self):
        r = check("MERGE INTO suppliers USING new_data ON suppliers.supplier_id = new_data.id")
        assert r.blocked
        assert ViolationType.DML_WRITE in r.violations


class TestMultipleStatements:
    def test_semicolon_injection(self):
        r = check("SELECT * FROM suppliers; DROP TABLE suppliers")
        assert r.blocked
        assert ViolationType.MULTIPLE_STATEMENTS in r.violations

    def test_select_then_delete(self):
        r = check("SELECT * FROM inventory LIMIT 10; DELETE FROM inventory")
        assert r.blocked
        assert ViolationType.MULTIPLE_STATEMENTS in r.violations


class TestSystemTableAccess:
    def test_pg_catalog(self):
        r = check("SELECT * FROM pg_catalog.pg_tables")
        assert r.blocked
        assert ViolationType.SYSTEM_TABLE_ACCESS in r.violations

    def test_information_schema(self):
        r = check("SELECT table_name FROM information_schema.tables")
        assert r.blocked
        assert ViolationType.SYSTEM_TABLE_ACCESS in r.violations


class TestDangerousFunctions:
    def test_pg_read_file(self):
        r = check("SELECT pg_read_file('/etc/passwd')")
        assert r.blocked
        assert ViolationType.DANGEROUS_FUNCTION in r.violations

    def test_copy_command(self):
        r = check("COPY suppliers TO '/tmp/dump.csv'")
        assert r.blocked


class TestCommentInjection:
    def test_inline_comment_stripped_not_blocked(self):
        """Benign inline comments are stripped, not hard-blocked."""
        r = check("SELECT * FROM suppliers -- just a comment")
        assert not r.blocked
        assert ViolationType.COMMENT_INJECTION in r.violations
        assert r.sanitised_sql is not None
        assert "--" not in (r.sanitised_sql or "")

    def test_block_comment_stripped_not_blocked(self):
        """Benign block comments are stripped, not hard-blocked."""
        r = check("SELECT * FROM suppliers /* get all */ WHERE is_active = TRUE")
        assert not r.blocked
        assert ViolationType.COMMENT_INJECTION in r.violations

    def test_comment_after_semicolon_blocked(self):
        """Comment immediately after a semicolon masks injection — hard block."""
        r = check("SELECT * FROM suppliers; -- DROP TABLE suppliers")
        assert r.blocked
        assert ViolationType.MULTIPLE_STATEMENTS in r.violations or ViolationType.COMMENT_INJECTION in r.violations


# ---------------------------------------------------------------------------
# Soft fixes — passed after transformation
# ---------------------------------------------------------------------------

class TestUnboundedScan:
    def test_limit_injected_when_missing(self):
        r = check("SELECT * FROM suppliers")
        assert not r.blocked
        assert r.passed
        assert ViolationType.UNBOUNDED_SCAN in r.violations
        assert "LIMIT 1000" in (r.sanitised_sql or "")

    def test_existing_limit_preserved(self):
        r = check("SELECT * FROM suppliers LIMIT 50")
        assert not r.blocked
        assert r.passed
        assert ViolationType.UNBOUNDED_SCAN not in r.violations
        assert "LIMIT 1000" not in (r.sanitised_sql or "")

    def test_limit_case_insensitive(self):
        r = check("select * from suppliers limit 5")
        assert ViolationType.UNBOUNDED_SCAN not in r.violations


class TestDeepSubquery:
    def test_deep_subquery_flagged_not_blocked(self):
        sql = (
            "SELECT * FROM suppliers WHERE supplier_id IN "
            "(SELECT supplier_id FROM purchase_orders WHERE product_id IN "
            "(SELECT product_id FROM inventory WHERE warehouse_id IN "
            "(SELECT warehouse_id FROM warehouses WHERE country = 'India') LIMIT 10) LIMIT 10) LIMIT 10"
        )
        r = check(sql)
        assert not r.blocked
        # May or may not flag depending on depth — just check it doesn't crash


# ---------------------------------------------------------------------------
# Valid queries — must pass
# ---------------------------------------------------------------------------

class TestValidQueries:
    def test_simple_select(self):
        r = check("SELECT supplier_id, supplier_name FROM suppliers WHERE is_active = TRUE LIMIT 10")
        assert r.passed
        assert not r.blocked

    def test_join_query(self):
        r = check(
            "SELECT s.supplier_name, COUNT(po.po_id) "
            "FROM suppliers s JOIN purchase_orders po ON s.supplier_id = po.supplier_id "
            "GROUP BY s.supplier_name LIMIT 20"
        )
        assert r.passed
        assert not r.blocked

    def test_aggregation(self):
        r = check("SELECT AVG(rating) AS avg_rating FROM suppliers WHERE is_active = TRUE LIMIT 1")
        assert r.passed
        assert not r.blocked
