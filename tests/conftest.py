import pytest

from retailpulse.config import Settings
from retailpulse.data import generate_synthetic


@pytest.fixture(scope="session")
def synthetic_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("raw")
    generate_synthetic(d, n_customers=2500, seed=7)
    return d


@pytest.fixture(scope="session")
def run_result(synthetic_dir, tmp_path_factory):
    """Full pipeline run on synthetic data (shared by the integration tests)."""
    from retailpulse import pipeline

    s = Settings(data_dir=synthetic_dir, artifacts_dir=tmp_path_factory.mktemp("artifacts"))
    metrics = pipeline.run(s, n_folds=2)
    return s, metrics
