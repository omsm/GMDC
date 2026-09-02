# Shared GMDC library
# Install editable so every app can `import gmdc_common`:
#   pip install -e .
from setuptools import find_packages, setup

setup(
    name="gmdc-common",
    version="0.1.0",
    description="Shared hardware, services and FSM for GMDC checkpoint apps",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "requests>=2.28",
        "pymodbus>=3.0",
        "paho-mqtt>=1.6",
    ],
)
