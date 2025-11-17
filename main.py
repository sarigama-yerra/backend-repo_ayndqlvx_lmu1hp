import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Literal, Dict, Any
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import AppUser, Video, Friend, Message

app = FastAPI(title="Video+Friends+Messaging API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utils
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)


def serialize_doc(doc: Dict[str, Any]):
    if not doc:
        return doc
    doc = dict(doc)
    _id = doc.get("_id")
    if isinstance(_id, ObjectId):
        doc["id"] = str(_id)
        del doc["_id"]
    # Convert nested ObjectIds if any
    for k, v in list(doc.items()):
        if isinstance(v, ObjectId):
            doc[k] = str(v)
    # Datetime to isoformat
    for k, v in list(doc.items()):
        try:
            if hasattr(v, "isoformat"):
                doc[k] = v.isoformat()
        except Exception:
            pass
    return doc


@app.get("/")
def read_root():
    return {"message": "Backend running"}


# Users
@app.post("/users", response_model=dict)
def create_user(user: AppUser):
    user_id = create_document("appuser", user)
    return {"id": user_id}


@app.get("/users", response_model=List[dict])
def list_users():
    docs = get_documents("appuser")
    return [serialize_doc(d) for d in docs]


# Videos
@app.post("/videos", response_model=dict)
def create_video(video: Video):
    # Basic sanity: uploader must exist
    uploader = db["appuser"].find_one({"_id": ObjectId(video.uploader_id)}) if ObjectId.is_valid(video.uploader_id) else None
    if not uploader:
        raise HTTPException(status_code=400, detail="Invalid uploader_id")
    vid_id = create_document("video", video)
    return {"id": vid_id}


@app.get("/videos", response_model=List[dict])
def list_videos(limit: Optional[int] = Query(default=20, ge=1, le=100)):
    cursor = db["video"].find({}).sort("created_at", -1).limit(limit)
    return [serialize_doc(d) for d in cursor]


# Friends
class FriendRequest(BaseModel):
    to_user_id: str
    from_user_id: str


@app.post("/friends/request", response_model=dict)
def request_friend(req: FriendRequest):
    for uid in [req.to_user_id, req.from_user_id]:
        if not ObjectId.is_valid(uid):
            raise HTTPException(status_code=400, detail="Invalid user id")
    if req.to_user_id == req.from_user_id:
        raise HTTPException(status_code=400, detail="Cannot friend yourself")

    # Check existing relationship
    exists = db["friend"].find_one({
        "$or": [
            {"user_a": req.from_user_id, "user_b": req.to_user_id},
            {"user_a": req.to_user_id, "user_b": req.from_user_id},
        ]
    })
    if exists and exists.get("status") in ["pending", "accepted"]:
        raise HTTPException(status_code=400, detail="Friend request already exists")

    doc = Friend(user_a=req.from_user_id, user_b=req.to_user_id, status="pending", requester=req.from_user_id)
    fid = create_document("friend", doc)
    return {"id": fid}


class FriendRespond(BaseModel):
    friend_id: str
    action: Literal["accept", "reject"]
    user_id: str


@app.post("/friends/respond", response_model=dict)
def respond_friend(body: FriendRespond):
    if not ObjectId.is_valid(body.friend_id):
        raise HTTPException(status_code=400, detail="Invalid friend_id")
    rel = db["friend"].find_one({"_id": ObjectId(body.friend_id)})
    if not rel:
        raise HTTPException(status_code=404, detail="Request not found")
    if body.user_id not in [rel.get("user_a"), rel.get("user_b")]:
        raise HTTPException(status_code=403, detail="Not authorized to respond")

    new_status = "accepted" if body.action == "accept" else "rejected"
    db["friend"].update_one({"_id": ObjectId(body.friend_id)}, {"$set": {"status": new_status}})
    return {"status": new_status}


@app.get("/friends/{user_id}", response_model=List[dict])
def get_friends(user_id: str):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id")
    cursor = db["friend"].find({
        "$or": [{"user_a": user_id}, {"user_b": user_id}]
    })
    rels = [serialize_doc(d) for d in cursor]
    # Enrich with other user info
    for r in rels:
        other_id = r["user_b"] if r["user_a"] == user_id else r["user_a"]
        other = db["appuser"].find_one({"_id": ObjectId(other_id)}) if ObjectId.is_valid(other_id) else None
        r["other_user"] = serialize_doc(other) if other else None
    return rels


# Messages
class SendMessage(BaseModel):
    sender_id: str
    receiver_id: str
    content: str


@app.post("/messages", response_model=dict)
def send_message(body: SendMessage):
    for uid in [body.sender_id, body.receiver_id]:
        if not ObjectId.is_valid(uid):
            raise HTTPException(status_code=400, detail="Invalid user id")
    # Optionally ensure friendship accepted
    accepted = db["friend"].find_one({
        "$or": [
            {"user_a": body.sender_id, "user_b": body.receiver_id},
            {"user_a": body.receiver_id, "user_b": body.sender_id},
        ],
        "status": "accepted",
    })
    if not accepted:
        raise HTTPException(status_code=403, detail="You must be friends to message")

    mid = create_document("message", Message(**body.dict()))
    return {"id": mid}


@app.get("/messages", response_model=List[dict])
def list_messages(user_a: str, user_b: str, limit: int = Query(default=100, ge=1, le=500)):
    if not ObjectId.is_valid(user_a) or not ObjectId.is_valid(user_b):
        raise HTTPException(status_code=400, detail="Invalid user ids")
    cursor = db["message"].find({
        "$or": [
            {"sender_id": user_a, "receiver_id": user_b},
            {"sender_id": user_b, "receiver_id": user_a},
        ]
    }).sort("created_at", 1).limit(limit)
    return [serialize_doc(d) for d in cursor]


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
