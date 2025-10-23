"""Tests to ensure Pydantic models generate valid OpenAI structured output schemas."""

import pytest
from models.planner_output import PlannerOutput
from models.planner_output_minimal import PlannerOutputMinimal
from models.planner_output_standard import PlannerOutputStandard


def check_schema_for_dict_without_additional_properties(schema, path=""):
    """
    Recursively check that all object types in the schema have additionalProperties: false.

    OpenAI requires all objects in structured output schemas to explicitly set
    additionalProperties to false.
    """
    issues = []

    if isinstance(schema, dict):
        # Check if this is an object type definition
        if schema.get("type") == "object":
            if "additionalProperties" not in schema or schema.get("additionalProperties") is not False:
                issues.append(f"Object at {path} missing 'additionalProperties: false'")

        # Check properties
        if "properties" in schema:
            for prop_name, prop_schema in schema["properties"].items():
                issues.extend(
                    check_schema_for_dict_without_additional_properties(
                        prop_schema, f"{path}.{prop_name}" if path else prop_name
                    )
                )

        # Check items (for arrays)
        if "items" in schema:
            issues.extend(
                check_schema_for_dict_without_additional_properties(
                    schema["items"], f"{path}.items"
                )
            )

        # Check definitions/defs (for nested schemas)
        for key in ["definitions", "$defs"]:
            if key in schema:
                for def_name, def_schema in schema[key].items():
                    issues.extend(
                        check_schema_for_dict_without_additional_properties(
                            def_schema, f"{path}.{key}.{def_name}"
                        )
                    )

    return issues


def test_planner_output_minimal_has_valid_schema():
    """Test that PlannerOutputMinimal generates a valid OpenAI schema."""
    schema = PlannerOutputMinimal.model_json_schema()
    issues = check_schema_for_dict_without_additional_properties(schema)

    if issues:
        print(f"\nSchema issues found in PlannerOutputMinimal:")
        for issue in issues:
            print(f"  - {issue}")

    assert len(issues) == 0, f"Found {len(issues)} schema validation issues"


def test_planner_output_standard_has_valid_schema():
    """Test that PlannerOutputStandard generates a valid OpenAI schema."""
    schema = PlannerOutputStandard.model_json_schema()
    issues = check_schema_for_dict_without_additional_properties(schema)

    if issues:
        print(f"\nSchema issues found in PlannerOutputStandard:")
        for issue in issues:
            print(f"  - {issue}")

    assert len(issues) == 0, f"Found {len(issues)} schema validation issues"


def test_planner_output_full_has_valid_schema():
    """Test that PlannerOutput (full) generates a valid OpenAI schema."""
    schema = PlannerOutput.model_json_schema()
    issues = check_schema_for_dict_without_additional_properties(schema)

    if issues:
        print(f"\nSchema issues found in PlannerOutput (full):")
        for issue in issues:
            print(f"  - {issue}")

    assert len(issues) == 0, f"Found {len(issues)} schema validation issues"


def test_group_by_columns_is_not_generic_dict():
    """Test that group_by_columns is properly typed, not a generic dict."""
    minimal_schema = PlannerOutputMinimal.model_json_schema()
    standard_schema = PlannerOutputStandard.model_json_schema()
    full_schema = PlannerOutput.model_json_schema()

    # Check in definitions/defs for GroupBySpec schemas
    for schema, name in [
        (minimal_schema, "PlannerOutputMinimal"),
        (standard_schema, "PlannerOutputStandard"),
        (full_schema, "PlannerOutput"),
    ]:
        # Find GroupBySpec in the schema definitions
        defs = schema.get("$defs", {})
        group_by_spec = None

        for def_name, def_schema in defs.items():
            if "GroupBySpec" in def_name:
                group_by_spec = def_schema
                break

        if group_by_spec:
            # Check that group_by_columns is properly typed
            props = group_by_spec.get("properties", {})
            group_by_columns = props.get("group_by_columns", {})

            # Should be an array
            assert group_by_columns.get("type") == "array", \
                f"{name}: group_by_columns should be an array"

            # Items should have a schema reference, not be a generic object
            items = group_by_columns.get("items", {})
            assert "$ref" in items or items.get("type") == "object", \
                f"{name}: group_by_columns items should have a schema"

            # If it's an object, it should have additionalProperties: false
            if items.get("type") == "object":
                assert items.get("additionalProperties") is False, \
                    f"{name}: group_by_columns items must have additionalProperties: false"


if __name__ == "__main__":
    test_planner_output_minimal_has_valid_schema()
    test_planner_output_standard_has_valid_schema()
    test_planner_output_full_has_valid_schema()
    test_group_by_columns_is_not_generic_dict()
    print("\n✅ All OpenAI schema validation tests passed!")
