"""Conversation endpoints — list, create, fetch (full thread), rename, delete."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.repositories.conversations import ConversationRepository, get_conversation_repository

router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])


class RenameIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


def _repo() -> ConversationRepository:
    return get_conversation_repository()


@router.get("", summary="List conversations (summaries, newest first)")
def list_conversations():
    return _repo().list_all()


@router.post("", summary="Create an empty conversation")
def create_conversation(payload: dict | None = None):
    title = (payload or {}).get("title", "New chat")
    return _repo().create(title)


@router.get("/{conversation_id}", summary="Get a full conversation thread")
def get_conversation(conversation_id: str):
    conv = _repo().get(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conv


@router.patch("/{conversation_id}", summary="Rename a conversation")
def rename_conversation(conversation_id: str, payload: RenameIn):
    if not _repo().rename(conversation_id, payload.title):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"renamed": conversation_id, "title": payload.title}


@router.delete("/{conversation_id}", summary="Delete a conversation")
def delete_conversation(conversation_id: str):
    if not _repo().delete(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"deleted": conversation_id}
