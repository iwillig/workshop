import hegel
from hegel import generators as gs

from research_context.github import repository_path


@hegel.test
def test_repository_path_preserves_numeric_owner_and_name(tc):
    owner = str(tc.draw(gs.integers(min_value=0)))
    name = str(tc.draw(gs.integers(min_value=0)))
    assert repository_path(f"{owner}/{name}") == f"/repos/{owner}/{name}"
