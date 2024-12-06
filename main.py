from fastapi import FastAPI, Depends, HTTPException, status, Request, File, UploadFile
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
import models
from database import SessionLocal, engine, get_db
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import speech_recognition as sr
from pydub import AudioSegment
import io
import tempfile
import os
from contextlib import asynccontextmanager
import subprocess
import shutil
# Add this near the top of your file with other imports
from fastapi.staticfiles import StaticFiles

# Add this after creating your FastAPI app
def get_ffmpeg_path():
    try:
        # Try running ffmpeg -version to get its path
        result = subprocess.run(['where', 'ffmpeg'], 
                              capture_output=True, 
                              text=True, 
                              check=True)
        ffmpeg_path = result.stdout.strip().split('\n')[0]
        print(f"Found FFmpeg at: {ffmpeg_path}")
        return ffmpeg_path
    except subprocess.CalledProcessError:
        # If where command fails, try common locations
        possible_paths = [
            os.path.join("C:", "Program Files", "ffmpeg", "bin", "ffmpeg.exe"),
            os.path.join("D:", "Program Files", "ffmpeg", "bin", "ffmpeg.exe"),
            os.path.join("C:", "ffmpeg", "bin", "ffmpeg.exe"),
            os.path.join("D:", "ffmpeg", "bin", "ffmpeg.exe"),
            r"C:\Users\Lenovo\AppData\Local\Microsoft\WindowsApps\ffmpeg.exe"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                print(f"Found FFmpeg at: {path}")
                return path
        
        print("WARNING: FFmpeg not found!")
        return None

# Get FFmpeg paths
FFMPEG_PATH = get_ffmpeg_path()
FFPROBE_PATH = FFMPEG_PATH.replace('ffmpeg.exe', 'ffprobe.exe') if FFMPEG_PATH else None

if FFMPEG_PATH:
    # Configure pydub
    AudioSegment.converter = FFMPEG_PATH
    AudioSegment.ffmpeg = FFMPEG_PATH
    AudioSegment.ffprobe = FFPROBE_PATH
    
    # Add FFmpeg directory to PATH
    os.environ["PATH"] += os.pathsep + os.path.dirname(FFMPEG_PATH)
    
    print(f"Using FFmpeg at: {FFMPEG_PATH}")
    print(f"Using FFprobe at: {FFPROBE_PATH}")

# Create database tables
models.Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Loading ML model and other startup tasks")
    yield
    # Shutdown
    print("Cleaning up resources")

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
# Static files and templates
templates = Jinja2Templates(directory="templates")

# Security
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Add authentication dependency
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(models.UserModel).filter(models.UserModel.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# Routes
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = next(get_db())
    try:
        # Get the test user
        user = db.query(models.UserModel).filter_by(username="test@example.com").first()
        
        # Get user's bookings with schedule details
        bookings = (
            db.query(models.BookingModel, models.ScheduleModel)
            .join(models.ScheduleModel)
            .filter(models.BookingModel.user_id == user.id)
            .order_by(models.BookingModel.booking_date.desc())
            .all()
        )
        
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "user": user,
                "bookings": bookings
            }
        )
    finally:
        db.close()

@app.post("/register")
async def register(
    username: str,
    email: str,
    password: str,
    db: Session = Depends(get_db)
):
    user = models.UserModel(
        username=username,
        email=email,
        hashed_password=get_password_hash(password)
    )
    db.add(user)
    db.commit()
    return {"message": "User created successfully"}

@app.post("/token")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    try:
        print(f"Attempting login with username: {form_data.username}")
        
        # Debug: Print all users in database
        all_users = db.query(models.UserModel).all()
        print("All users in database:", [user.username for user in all_users])
        
        user = db.query(models.UserModel).filter(
            models.UserModel.username == form_data.username
        ).first()
        
        if not user:
            print("User not found in database")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )
        
        print("Found user:", user.username)
        
        if not verify_password(form_data.password, user.hashed_password):
            print("Password verification failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )
        
        print("Login successful")
        return {
            "access_token": "dummy_token",
            "token_type": "bearer",
            "redirect_url": "/dashboard"
        }
    except Exception as e:
        print(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

# Populate database with dummy data
def populate_dummy_data(db: Session):
    # Check if test user already exists
    existing_user = db.query(models.UserModel).filter(
        models.UserModel.username == "test@example.com"
    ).first()
    
    if not existing_user:
        print("Creating test user...")
        test_user = models.UserModel(
            username="test@example.com",
            email="test@example.com",
            hashed_password=get_password_hash("password123")
        )
        db.add(test_user)
        try:
            db.commit()
            print("Test user created successfully")
        except Exception as e:
            print(f"Error creating test user: {str(e)}")
            db.rollback()
            return
    
    # Create schedules if they don't exist
    if db.query(models.ScheduleModel).count() == 0:
        schedules = [
            {
                "departure": "New York",
                "destination": "London",
                "departure_time": datetime.now() + timedelta(days=1),
                "arrival_time": datetime.now() + timedelta(days=1, hours=7),
                "price": 500.00,
                "available_seats": 100
            },
            {
                "departure": "Paris",
                "destination": "Tokyo",
                "departure_time": datetime.now() + timedelta(days=2),
                "arrival_time": datetime.now() + timedelta(days=2, hours=12),
                "price": 800.00,
                "available_seats": 150
            },
            {
                "departure": "Dubai",
                "destination": "Singapore",
                "departure_time": datetime.now() + timedelta(days=3),
                "arrival_time": datetime.now() + timedelta(days=3, hours=6),
                "price": 400.00,
                "available_seats": 120
            }
        ]
        
        for schedule_data in schedules:
            schedule = models.ScheduleModel(**schedule_data)
            db.add(schedule)
        
        try:
            db.commit()
            print("Schedules created successfully")
        except Exception as e:
            print(f"Error creating schedules: {str(e)}")
            db.rollback()
            return

    # Create dummy bookings if they don't exist
    if db.query(models.BookingModel).count() == 0:
        # Get the test user and schedules
        user = db.query(models.UserModel).filter_by(username="test@example.com").first()
        schedules = db.query(models.ScheduleModel).all()
        
        bookings = [
            {
                "user_id": user.id,
                "schedule_id": schedules[0].id,
                "booking_date": datetime.now() - timedelta(days=5),
                "status": "Confirmed",
                "seat_number": "A1"
            },
            {
                "user_id": user.id,
                "schedule_id": schedules[1].id,
                "booking_date": datetime.now() - timedelta(days=3),
                "status": "Cancelled",
                "seat_number": "B2"
            },
            {
                "user_id": user.id,
                "schedule_id": schedules[2].id,
                "booking_date": datetime.now() - timedelta(days=1),
                "status": "Pending",
                "seat_number": "C3"
            }
        ]
        
        for booking_data in bookings:
            booking = models.BookingModel(**booking_data)
            db.add(booking)
        
        try:
            db.commit()
            print("Dummy bookings created successfully")
        except Exception as e:
            print(f"Error creating dummy bookings: {str(e)}")
            db.rollback()

# Populate database on startup
@app.on_event("startup")
async def startup_event():
    db = next(get_db())
    try:
        populate_dummy_data(db)
    finally:
        db.close()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization"],
    expose_headers=["Authorization"],
)

# Add this helper function to check auth headers
async def get_token_from_header(request: Request) -> str:
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication scheme"
            )
        return token
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format"
        )

@app.get("/book-ticket", response_class=HTMLResponse)
async def book_ticket(request: Request):
    return templates.TemplateResponse(
        "book_ticket.html",
        {
            "request": request,
            "user": {"username": "User"}
        }
    )

@app.get("/view-schedule", response_class=HTMLResponse)
async def view_schedule(
    request: Request,
    departure: str = None,
    destination: str = None,
    date: str = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.ScheduleModel)
    
    if departure:
        query = query.filter(models.ScheduleModel.departure == departure)
    if destination:
        query = query.filter(models.ScheduleModel.destination == destination)
    if date:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        next_day = date_obj + timedelta(days=1)
        query = query.filter(
            models.ScheduleModel.departure_time >= date_obj,
            models.ScheduleModel.departure_time < next_day
        )
    
    schedules = query.all()
    
    # Get unique cities for filters
    cities = db.query(models.ScheduleModel.departure).union(
        db.query(models.ScheduleModel.destination)
    ).distinct().all()
    cities = [city[0] for city in cities]
    
    return templates.TemplateResponse(
        "view_schedule.html",
        {
            "request": request,
            "schedules": schedules,
            "cities": cities
        }
    )

@app.get("/cancel-ticket", response_class=HTMLResponse)
async def cancel_ticket_page(
    request: Request,
    db: Session = Depends(get_db)
):
    user = db.query(models.UserModel).filter_by(username="test@example.com").first()
    
    bookings = (
        db.query(models.BookingModel, models.ScheduleModel)
        .join(models.ScheduleModel)
        .filter(
            models.BookingModel.user_id == user.id,
            models.BookingModel.status != 'Cancelled'
        )
        .order_by(models.BookingModel.booking_date.desc())
        .all()
    )
    
    return templates.TemplateResponse(
        "cancel_ticket.html",
        {
            "request": request,
            "bookings": bookings
        }
    )

@app.post("/api/book-ticket")
async def book_ticket(
    schedule_id: int,
    seat_type: str,
    db: Session = Depends(get_db)
):
    user = db.query(models.UserModel).filter_by(username="test@example.com").first()
    schedule = db.query(models.ScheduleModel).filter_by(id=schedule_id).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    if schedule.available_seats <= 0:
        raise HTTPException(status_code=400, detail="No seats available")
    
    # Generate a seat number (simplified)
    seat_number = f"{seat_type[0].upper()}{schedule.available_seats}"
    
    booking = models.BookingModel(
        user_id=user.id,
        schedule_id=schedule_id,
        status="Confirmed",
        seat_number=seat_number
    )
    
    schedule.available_seats -= 1
    
    db.add(booking)
    db.commit()
    
    return {"message": "Booking successful", "booking_id": booking.id}

@app.post("/api/cancel-booking/{booking_id}")
async def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db)
):
    booking = db.query(models.BookingModel).filter_by(id=booking_id).first()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    if booking.status == "Cancelled":
        raise HTTPException(status_code=400, detail="Booking already cancelled")
    
    booking.status = "Cancelled"
    
    # Return the seat to available seats
    schedule = db.query(models.ScheduleModel).filter_by(id=booking.schedule_id).first()
    schedule.available_seats += 1
    
    db.commit()
    
    return {"message": "Booking cancelled successfully"}

def extract_city_after(keyword: str, text: str) -> str:
    # Dummy implementation - just for demonstration
    print(f"Attempting to extract city after '{keyword}' from: {text}")
    return "dummy_city"

def extract_booking_id(text: str) -> int:
    # Dummy implementation - just for demonstration
    print(f"Attempting to extract booking ID from: {text}")
    return 123

@app.post("/process-voice")
async def process_voice(audio: UploadFile = File(...)):
    temp_original = None
    temp_wav = None
    
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        
        # Create paths for our temporary files
        temp_original = os.path.join(temp_dir, 'original.webm')
        temp_wav = os.path.join(temp_dir, 'converted.wav')
        
        # Read and save the uploaded audio
        audio_data = await audio.read()
        with open(temp_original, 'wb') as f:
            f.write(audio_data)
        
        print(f"Saved original audio to: {temp_original}")
        
        try:
            # Convert webm to wav using FFmpeg directly
            print("Converting audio to WAV...")
            cmd = [
                FFMPEG_PATH,
                '-i', temp_original,
                '-acodec', 'pcm_s16le',
                '-ac', '1',
                '-ar', '16000',
                temp_wav
            ]
            
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            if process.returncode != 0:
                print(f"FFmpeg error: {process.stderr.decode()}")
                raise Exception("FFmpeg conversion failed")
                
            print(f"Converted audio saved to: {temp_wav}")
            
            # Initialize recognizer
            r = sr.Recognizer()
            
            # Use recognizer to convert speech to text
            print("Processing audio with speech recognition...")
            with sr.AudioFile(temp_wav) as source:
                audio_data = r.record(source)
                text = r.recognize_google(audio_data).lower()
                print(f"Recognized voice command: {text}")  # Terminal output

                # Enhanced command processing with dummy responses
                if "book" in text:
                    print("Detected booking command")
                    return {
                        "command": "book",
                        "message": f"Recognized command: {text}",
                        "flightDetails": {
                            "from": extract_city_after("from", text),
                            "to": extract_city_after("to", text)
                        }
                    }
                elif "cancel" in text:
                    print("Detected cancellation command")
                    return {
                        "command": "cancel",
                        "message": f"Recognized command: {text}",
                        "bookingId": extract_booking_id(text)
                    }
                elif "schedule" in text or "flight" in text:
                    print("Detected schedule command")
                    return {
                        "command": "search",
                        "message": f"Recognized command: {text}",
                        "searchDetails": {
                            "from": extract_city_after("from", text),
                            "to": extract_city_after("to", text),
                            "date": None
                        }
                    }
                else:
                    print(f"Command not recognized: {text}")
                    return {
                        "command": None, 
                        "message": f"Heard: {text} (Command not recognized)"
                    }

        except Exception as e:
            print(f"Error during audio processing: {str(e)}")
            raise e

    except Exception as e:
        print(f"Error processing voice: {str(e)}")
        return {"error": str(e)}
        
    finally:
        # Clean up temporary files
        try:
            if temp_original and os.path.exists(temp_original):
                os.remove(temp_original)
            if temp_wav and os.path.exists(temp_wav):
                os.remove(temp_wav)
            if 'temp_dir' in locals():
                shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Error cleaning up temporary files: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 