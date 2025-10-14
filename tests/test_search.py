import pytest

from localbooru import search


@pytest.mark.parametrize(
    "query, expected_params",
    [
        ("dark-skinned_female", ['norm:"dark-skinned_female"']),
        (
            "tag1, dark-skinned_female",
            ['norm:"tag1"', 'norm:"dark-skinned_female"'],
        ),
        (
            "-dark-skinned_female",
            ['norm:"dark-skinned_female"'],
        ),
    ],
)
def test_build_matched_cte_quotes_tokens(query, expected_params):
    tokens = search.tokens_from_query(query)
    cte, params = search.build_matched_cte(tokens)

    # Ensure the generated CTE references the matched table.
    assert "WITH matched AS" in cte
    # Parameters should be quoted so that FTS treats them as string tokens.
    assert params == expected_params


def test_tokens_from_query_preserves_hyphen():
    tokens = search.tokens_from_query("dark-skinned_female")
    assert tokens == [("dark-skinned_female", "any", False)]
