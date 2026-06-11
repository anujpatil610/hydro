def test_ml_package_imports():
    import ml
    import ml.data
    import ml.models

    assert ml.__version__ == "0.1.0"


def test_sklearn_available_at_required_version():
    import sklearn

    major, minor = (int(x) for x in sklearn.__version__.split(".")[:2])
    assert (major, minor) >= (1, 4)
