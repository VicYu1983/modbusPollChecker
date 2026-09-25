from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .check_service import CheckService
from .schemas import CheckRequest, DeviceConfig, ErrorResponse, SiteConfig
from .site_store import SiteStore


ROOT = Path(__file__).resolve().parents[2]
store = SiteStore(ROOT / "data" / "site.json")
check_service = CheckService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    check_service.shutdown()


app = FastAPI(title="Modbus Poll Checker API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exception: RequestValidationError) -> JSONResponse:
    details = [
        {
            "field": ".".join(str(part) for part in error["loc"] if part != "body"),
            "message": error["msg"],
        }
        for error in exception.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "設定驗證失敗",
            "details": details,
        },
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/site", response_model=SiteConfig)
def get_site() -> SiteConfig:
    return store.load()


@app.post("/api/site/import", response_model=SiteConfig)
def import_site(config: SiteConfig) -> SiteConfig:
    return store.save(config)


@app.get("/api/site/export", response_model=SiteConfig)
def export_site() -> SiteConfig:
    return store.load()


@app.post("/api/devices", response_model=DeviceConfig, responses={409: {"model": ErrorResponse}})
def add_device(device: DeviceConfig) -> DeviceConfig:
    config = store.load()
    if any(existing.name == device.name for existing in config.devices):
        raise HTTPException(status_code=409, detail="device name already exists")
    config.devices.append(device)
    store.save(config)
    return device


@app.put("/api/devices/{name}", response_model=DeviceConfig)
def update_device(name: str, device: DeviceConfig) -> DeviceConfig:
    config = store.load()
    index = next((index for index, item in enumerate(config.devices) if item.name == name), None)
    if index is None:
        raise HTTPException(status_code=404, detail="device not found")
    if device.name != name and any(item.name == device.name for item in config.devices):
        raise HTTPException(status_code=409, detail="device name already exists")
    config.devices[index] = device
    store.save(config)
    return device


@app.delete("/api/devices/{name}", status_code=204)
def delete_device(name: str) -> Response:
    config = store.load()
    devices = [device for device in config.devices if device.name != name]
    if len(devices) == len(config.devices):
        raise HTTPException(status_code=404, detail="device not found")
    store.save(config.model_copy(update={"devices": devices}))
    return Response(status_code=204)


@app.post("/api/check")
def check_devices(request: CheckRequest) -> list[dict[str, object]]:
    config = store.load()
    if request.device_name and not any(device.name == request.device_name for device in config.devices):
        raise HTTPException(status_code=404, detail="device not found")
    return [result.model_dump(mode="json") for result in check_service.check(config, request.device_name)]


@app.get("/api/status")
def get_status() -> list[dict[str, object]]:
    return [result.model_dump(mode="json") for result in check_service.status()]


@app.post("/api/polling/start")
def start_polling() -> dict[str, object]:
    started = check_service.start_polling(store.load)
    return {"started": started, "status": check_service.polling_status().model_dump(mode="json")}


@app.post("/api/polling/stop")
def stop_polling() -> dict[str, object]:
    stopped = check_service.stop_polling()
    return {"stopped": stopped, "status": check_service.polling_status().model_dump(mode="json")}


@app.get("/api/polling/status")
def get_polling_status() -> dict[str, object]:
    return check_service.polling_status().model_dump(mode="json")
