#!/usr/bin/env bash
# Exit on error
set -o errexit

# Upgrade pip to avoid metadata generation errors with newer packages
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
