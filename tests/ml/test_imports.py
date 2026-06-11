def test_ml_package_imports():
    import ml
    import ml.data
    import ml.models

    assert ml.__version__ == "0.1.0"


def test_sklearn_available_at_required_version():
    import sklearn
    from packaging.version import Version

    assert Version(sklearn.__version__) >= Version("1.4")
