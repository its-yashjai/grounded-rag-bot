"""Test isolation: keep tests away from the real on-disk stores (Chroma,
knowledge-base JSON, SQLite chats). Must set env before app.config loads."""
import os

os.environ["CHROMA_PERSIST_DIR"] = "./data/test_store/chroma"
os.environ["UPLOAD_DIR"] = "./data/test_store/uploads"
# The cross-encoder downloads a model from Hugging Face on first use. Keep the
# API integration tests offline; the reranker selection itself is covered by
# the unit tests in test_core_units.py.
os.environ.setdefault("ENABLE_CROSS_ENCODER_RERANKER", "false")
