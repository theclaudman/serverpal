from fastapi import FastAPI, WebSocket

app = FastAPI()

@app.websocket("/ws/test")
async def test_ws(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_text("hello")
    await websocket.close()

@app.get("/")
async def root():
    return {"status": "ok"}