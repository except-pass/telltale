from setuptools import setup, find_packages

setup(
    name="telltale",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "neo4j>=5.9.0",
        "click>=8.1.3",
        "pydantic>=2.0.0",
        "typer>=0.9.0",
        "rich>=13.0.0",
    ],
    entry_points={
        "console_scripts": [
            "telltale=telltale.cli.main:app",
        ],
    },
    author="Your Name",
    author_email="your.email@example.com",
    description="Knowledge Graph-Based Diagnostic Assistant",
    keywords="diagnostics, neo4j, graph database",
    python_requires=">=3.8",
) 