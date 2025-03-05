from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel
from sqlmodel import Session, select, or_, and_
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
from models import FriendRequest, FriendRequestCreate, Invite, User, UserCreate, UserLogin, UserProfile, create_access_token, create_db_and_tables, get_db, get_password_hash, verify_password

app = FastAPI()

@app.on_event("startup")
def on_startup():
    create_db_and_tables()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*", "GET", "POST"],
    allow_headers=["*"],
)


@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.exec(select(User).where(User.username == user.username)).first()
    if existing_user: 
        raise HTTPException(status_code=400, detail="Username already exits")
    
    hashed_password = get_password_hash(user.password)
    db_user = User(username=user.username, password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return {"message": "User registered successfully", "success": True}


@app.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.exec(select(User).where(User.username == user.username)).first()
    is_password_verified = verify_password(user.password, db_user.password)
    if not db_user or not is_password_verified:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentails")

    access_token = create_access_token({"id": db_user.id, "username": db_user.username, "rating": db_user.rating})
    return {"user": db_user.model_dump(), "access_token": access_token}



@app.get("/get-all-users", response_model=list[UserProfile])
def get_all_users(db: Session = Depends(get_db)):
    users = db.exec(select(User)).all()
    return users


@app.post("/send-friend-request")
def send_friend_request(request: FriendRequestCreate, db: Session = Depends(get_db)):
    friend_request = FriendRequest(sender_id=request.sender_id, receiver_id=request.receiver_id, status="PENDING")
    db.add(friend_request)
    db.commit()
    
    return {"message": "Friend request sent"}


@app.get("/friend-requests/{user_id}")
def friend_requests(user_id: int, db: Session = Depends(get_db)):
    friend_requests = db.exec(
        select(FriendRequest).where(
            and_(
                FriendRequest.receiver_id == user_id,
                FriendRequest.status == "PENDING" 
            )
        )
    ).all() 

    friend_requests_users = []
    for friend_request in friend_requests:
        user = db.exec(select(User).where(User.id == friend_request.sender_id)).first()
        request = {
            "sender": user.model_dump(),
            "request_id": friend_request.id
        }

        friend_requests_users.append(request)
    
    return {"friends": friend_requests_users}


@app.post("/respond-friend-request/{request_id}")
def respond_friend_request(request_id: int, response: str,  db: Session = Depends(get_db)):
    friend_request = db.exec(select(FriendRequest).where(FriendRequest.id == request_id)).first()
    if not friend_request: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friend request not found")
    
    friend_request.status = response 
    db.commit() 
    
    return {"message": f"Friend request {response}"}


@app.get("/search-friends")
def search_friends(username: str, db: Session = Depends(get_db)): 
    friend = db.exec(select(User).where(User.username == username)).first()
    if not friend:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found!")

    return {"friend": friend.model_dump()}


@app.get("/get-user/{id}")
def get_user(id: int, db: Session = Depends(get_db)): 
    user = db.exec(select(User).where(User.id == id)).first() 
    if not user: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, details="User not found!")
    
    return {"user": user.model_dump()}


@app.get("/get-all-friends/{request_id}")
def get_all_friends(request_id: int, db: Session = Depends(get_db)):
    friends = db.exec(
        select(FriendRequest).where(
            and_(
                or_(
                    FriendRequest.sender_id == request_id,
                    FriendRequest.receiver_id == request_id
                ),
                FriendRequest.status == "ACCEPTED" 
            )
        )
    ).all() 

    friend_id = []
    for friend in friends: 
        if friend.sender_id == request_id: 
            friend_id.append(friend.receiver_id)
        elif friend.receiver_id == request_id: 
            friend_id.append(friend.sender_id)

    friends = []
    for id in friend_id:
        user = db.exec(select(User).where(User.id == id)).first() 
        friends.append(user.model_dump())
    
    return {"friends": friends}


@app.post("/invite/{inviter_username}/{invitee_username}/{turn}/{inviter_rating}/{invitee_rating}")
def invite(inviter_username: str, invitee_username: str, turn: str, inviter_rating: int, invitee_rating: int, db: Session = Depends(get_db)): 
    invite = Invite(inviter=inviter_username, invitee=invitee_username)
    db.add(invite)
    db.commit()

    inviter_link = ""
    invitee_link = ""

    if turn == "goat":
        inviter_link = f"http://localhost:3000/online?room={invite.id}&you=goat&user={invitee_username}&rating={invitee_rating}"
        invitee_link = f"http://localhost:3000/online?room={invite.id}&you=tiger&user={inviter_username}&rating={inviter_rating}"
    else: 
        inviter_link = f"http://localhost:3000/online?room={invite.id}&you=tiger&user={invitee_username}&rating={invitee_rating}"
        invitee_link = f"http://localhost:3000/online?room={invite.id}&you=goat&user={inviter_username}&rating={inviter_rating}"
     
    
    invite.inviter_link = inviter_link
    invite.invitee_link = invitee_link

    db.commit()
    return {"invites": [inviter_link, invitee_link]} 


@app.get("/view-invites/{request_username}")
def view_invites(request_username: str, db: Session = Depends(get_db)): 
    invites = db.exec(select(Invite).where(Invite.invitee == request_username, Invite.status == "SENT")).all()
    return {"invites": invites}


@app.post("/update-rating/{username}/{score}")
def update_rating(username: str, score: int, db: Session = Depends(get_db)):
    print("username", username, score)
    user = db.exec(select(User).where(User.username == username)).first() 
    print("database user", user)
    
    user.rating += score
    if user.rating < 0:
        user.rating = 0
    
    db.commit()
    return {"rating": user.rating}


@app.delete("/remove-notification/{notification_id}/{status}")
def remove_notification(notification_id: int, status: str, db: Session = Depends(get_db)):
    notification = db.exec(select(Invite).where(Invite.id == notification_id)).first() 
    notification.status = status
    db.commit()
    return {"message": "Notification updated!"}


@app.get("/notification-status/{notification_id}/{username}")
def notification_status(notification_id: int, username: str, db: Session = Depends(get_db)): 
    notification = db.exec(select(Invite).where(Invite.id == notification_id, Invite.invitee == username)).first() 

    if notification:
        if notification.invitee == username and notification.status == "REJECTED":
            return {"status": "REJECTED", "notification": notification.model_dump()} 

    return {"status": "SENT"} 

 

if __name__ == "__main__":
    create_db_and_tables()

    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
