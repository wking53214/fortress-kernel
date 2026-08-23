"""Setup for FORTRESS Unified Kernel."""

from setuptools import setup, find_packages

setup(
    name="fortress-kernel",
    version="1.0.0",
    description="FORTRESS Unified Governance Kernel - Multi-controller safety orchestration",
    author="William King",
    author_email="wking53214@gmail.com",
    url="https://github.com/wking53214/fortress-kernel",
    packages=find_packages(),
    install_requires=[
        "numpy>=1.24.0",
    ],
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
