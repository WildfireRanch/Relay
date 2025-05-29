from fastapi import FastAPI
from routes import ask, status, control

app = FastAPI()

# Include route files
app.include_router(ask.router)
app.include_router(status.router)
app.include_router(control.router)

@app.get("/")
def root():
    return {"message": "Relay Agent is Online"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
