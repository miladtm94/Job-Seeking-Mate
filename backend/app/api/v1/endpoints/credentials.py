"""CRUD endpoints for saved (encrypted) platform credentials."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import credential_store

router = APIRouter(prefix="/credentials", tags=["credentials"])


class CredentialIn(BaseModel):
    email: str
    password: str


class CredentialOut(BaseModel):
    platform: str
    email: str


@router.get("/", response_model=list[CredentialOut])
def list_credentials():
    """Return email (no password) for each platform that has saved credentials."""
    result = []
    for platform in credential_store.list_saved():
        cred = credential_store.load(platform)
        if cred:
            result.append(CredentialOut(platform=platform, email=cred["email"]))
    return result


@router.get("/{platform}", response_model=CredentialOut)
def get_credential(platform: str):
    """Return email for the given platform (no password in response)."""
    cred = credential_store.load(platform)
    if not cred:
        raise HTTPException(404, f"No saved credentials for {platform!r}")
    return CredentialOut(platform=platform, email=cred["email"])


@router.post("/{platform}", response_model=CredentialOut)
def save_credential(platform: str, body: CredentialIn):
    """Encrypt and save credentials for the given platform."""
    try:
        credential_store.save(platform, body.email, body.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return CredentialOut(platform=platform, email=body.email)


@router.delete("/{platform}")
def delete_credential(platform: str):
    """Remove saved credentials for the given platform."""
    credential_store.delete(platform)
    return {"deleted": True, "platform": platform}


@router.get("/{platform}/full")
def get_credential_full(platform: str):
    """Return email AND password — used internally by the apply WebSocket."""
    cred = credential_store.load(platform)
    if not cred:
        raise HTTPException(404, f"No saved credentials for {platform!r}")
    return cred
