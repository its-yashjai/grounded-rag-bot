"""Test isolation: keep tests away from the real on-disk stores (Chroma,
knowledge-base JSON, SQLite chats). Must set env before app.config loads."""
import os

os.environ["CHROMA_PERSIST_DIR"] = "./data/test_store/chroma"
os.environ["UPLOAD_DIR"] = "./data/test_store/uploads"
