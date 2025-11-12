from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="netcup-api-filter",
    version="1.0.0",
    author="volkb79-2",
    description="A security proxy for the Netcup DNS API that provides granular access control",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/volkb79-2/netcup-api-filter",
    py_modules=["filter_proxy", "netcup_client", "access_control"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Networking",
        "Topic :: Security",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.7",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "netcup-api-filter=filter_proxy:main",
        ],
    },
)
