from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

app = FastAPI()

state = {"last_reading": None, "valve_open": False}

@app.get("/api/reading", response_class=PlainTextResponse)
def post_reading(value: float):
    state["last_reading"] = value
    return "OK"

@app.get("/api/valve", response_class=PlainTextResponse)
def get_valve():
    return "1" if state["valve_open"] else "0"

@app.get("/api/valve/set", response_class=PlainTextResponse)
def set_valve(open: bool):
    state["valve_open"] = open
    return "OK"

@app.get("/api/status")
def status():
    return state