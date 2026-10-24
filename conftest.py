"""Tests never inherit local provider credentials through dotenv discovery."""
import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
