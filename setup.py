from setuptools import setup, find_packages

setup(
    name="stonks",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=["click", "pandas", "yfinance", "scikit-learn", "pyyaml"],
    entry_points={
        "console_scripts": [
            "stonks=stonks_cli:cli"
        ]
    },
)
