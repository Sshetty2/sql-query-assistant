"""Test disconnected table validation in plan_audit."""

from agent.plan_audit import validate_table_connectivity


def test_single_table_no_joins():
    """Single table queries don't need joins."""
    plan = {
        "selections": [
            {"table": "tb_Company"}
        ],
        "join_edges": []
    }
    issues = validate_table_connectivity(plan)
    assert len(issues) == 0


def test_two_tables_with_join():
    """Two tables properly connected with join."""
    plan = {
        "selections": [
            {"table": "tb_Company"},
            {"table": "tb_SaasComputers"}
        ],
        "join_edges": [
            {
                "from_table": "tb_Company",
                "to_table": "tb_SaasComputers",
                "from_column": "ID",
                "to_column": "CompanyID"
            }
        ]
    }
    issues = validate_table_connectivity(plan)
    assert len(issues) == 0


def test_multiple_tables_no_joins():
    """Multiple tables with no joins should be flagged."""
    plan = {
        "selections": [
            {"table": "tb_Company"},
            {"table": "tb_CVE"}
        ],
        "join_edges": []
    }
    issues = validate_table_connectivity(plan)
    assert len(issues) == 1
    assert "no join edges defined" in issues[0]
    assert "CROSS JOIN" in issues[0]


def test_disconnected_table_cve_case():
    """The exact case from the CVE query failure."""
    plan = {
        "selections": [
            {"table": "tb_SaasComputers"},
            {"table": "tb_CVEConfigurationMap"},
            {"table": "tb_Company"},
            {"table": "tb_CVE"}
        ],
        "join_edges": [
            {
                "from_table": "tb_SaasComputers",
                "from_column": "ComputerID",
                "to_table": "tb_Company",
                "to_column": "ID"
            },
            {
                "from_table": "tb_CVEConfigurationMap",
                "from_column": "CVEID",
                "to_table": "tb_CVE",
                "to_column": "ID"
            }
        ]
    }

    # This should detect that we have two disconnected subgraphs:
    # Graph 1: tb_SaasComputers <-> tb_Company
    # Graph 2: tb_CVEConfigurationMap <-> tb_CVE
    # These are not connected to each other!

    issues = validate_table_connectivity(plan)
    assert len(issues) > 0

    # Should mention CROSS JOIN
    assert any("CROSS JOIN" in issue for issue in issues)

    # Should mention at least one disconnected table
    # (depends on which graph we start from in DFS)
    assert any("no join edges connecting it" in issue for issue in issues)


def test_three_tables_linear_chain():
    """Three tables in a linear chain A->B->C should be valid."""
    plan = {
        "selections": [
            {"table": "tb_A"},
            {"table": "tb_B"},
            {"table": "tb_C"}
        ],
        "join_edges": [
            {
                "from_table": "tb_A",
                "from_column": "ID",
                "to_table": "tb_B",
                "to_column": "A_ID"
            },
            {
                "from_table": "tb_B",
                "from_column": "ID",
                "to_table": "tb_C",
                "to_column": "B_ID"
            }
        ]
    }
    issues = validate_table_connectivity(plan)
    assert len(issues) == 0


def test_star_topology():
    """Star topology with central table should be valid."""
    plan = {
        "selections": [
            {"table": "tb_Center"},
            {"table": "tb_A"},
            {"table": "tb_B"},
            {"table": "tb_C"}
        ],
        "join_edges": [
            {
                "from_table": "tb_Center",
                "from_column": "ID",
                "to_table": "tb_A",
                "to_column": "CenterID"
            },
            {
                "from_table": "tb_Center",
                "from_column": "ID",
                "to_table": "tb_B",
                "to_column": "CenterID"
            },
            {
                "from_table": "tb_Center",
                "from_column": "ID",
                "to_table": "tb_C",
                "to_column": "CenterID"
            }
        ]
    }
    issues = validate_table_connectivity(plan)
    assert len(issues) == 0


def test_one_disconnected_table_in_group():
    """One table disconnected from a group of connected tables."""
    plan = {
        "selections": [
            {"table": "tb_A"},
            {"table": "tb_B"},
            {"table": "tb_C"},
            {"table": "tb_Orphan"}
        ],
        "join_edges": [
            {
                "from_table": "tb_A",
                "from_column": "ID",
                "to_table": "tb_B",
                "to_column": "A_ID"
            },
            {
                "from_table": "tb_B",
                "from_column": "ID",
                "to_table": "tb_C",
                "to_column": "B_ID"
            }
        ]
    }
    issues = validate_table_connectivity(plan)
    assert len(issues) == 1
    assert "tb_Orphan" in issues[0]
    assert "no join edges connecting it" in issues[0]


def test_bidirectional_joins():
    """Joins work in both directions (A->B or B->A doesn't matter)."""
    plan = {
        "selections": [
            {"table": "tb_A"},
            {"table": "tb_B"}
        ],
        "join_edges": [
            {
                "from_table": "tb_B",  # Note: B->A not A->B
                "from_column": "A_ID",
                "to_table": "tb_A",
                "to_column": "ID"
            }
        ]
    }
    issues = validate_table_connectivity(plan)
    assert len(issues) == 0


def test_join_to_non_selected_table_ignored():
    """Joins to tables not in selections should be ignored."""
    plan = {
        "selections": [
            {"table": "tb_A"},
            {"table": "tb_B"}
        ],
        "join_edges": [
            {
                "from_table": "tb_A",
                "from_column": "ID",
                "to_table": "tb_B",
                "to_column": "A_ID"
            },
            {
                # This join references tb_C which is NOT in selections
                # Should be ignored for connectivity purposes
                "from_table": "tb_A",
                "from_column": "ID",
                "to_table": "tb_C",
                "to_column": "A_ID"
            }
        ]
    }
    issues = validate_table_connectivity(plan)
    assert len(issues) == 0  # tb_A and tb_B are connected


def test_circular_joins():
    """Circular join graph should be valid."""
    plan = {
        "selections": [
            {"table": "tb_A"},
            {"table": "tb_B"},
            {"table": "tb_C"}
        ],
        "join_edges": [
            {
                "from_table": "tb_A",
                "from_column": "ID",
                "to_table": "tb_B",
                "to_column": "A_ID"
            },
            {
                "from_table": "tb_B",
                "from_column": "ID",
                "to_table": "tb_C",
                "to_column": "B_ID"
            },
            {
                "from_table": "tb_C",
                "from_column": "ID",
                "to_table": "tb_A",
                "to_column": "C_ID"
            }
        ]
    }
    issues = validate_table_connectivity(plan)
    assert len(issues) == 0
