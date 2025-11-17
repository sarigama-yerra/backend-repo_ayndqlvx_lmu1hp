"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal

# Core app schemas

class AppUser(BaseModel):
    """Users collection schema (collection name: "appuser")"""
    username: str = Field(..., description="Unique username")
    email: str = Field(..., description="Email address")
    avatar_url: Optional[str] = Field(None, description="Profile image URL")

class Video(BaseModel):
    """Videos collection schema (collection name: "video")"""
    title: str = Field(..., description="Video title")
    url: str = Field(..., description="Public video URL (mp4, YouTube, etc.)")
    description: Optional[str] = Field(None, description="Short description")
    uploader_id: str = Field(..., description="ID of user who uploaded")
    thumbnail_url: Optional[str] = Field(None, description="Thumbnail URL")

class Friend(BaseModel):
    """Friend relationships (collection name: "friend")"""
    user_a: str = Field(..., description="First user id")
    user_b: str = Field(..., description="Second user id")
    status: Literal["pending", "accepted", "rejected"] = Field("pending")
    requester: str = Field(..., description="User id who initiated the request")

class Message(BaseModel):
    """Direct messages between two users (collection name: "message")"""
    sender_id: str
    receiver_id: str
    content: str
