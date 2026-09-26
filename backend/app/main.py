from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from urllib.parse import quote

from .check_service import CheckService
from .domain.models import (
    BatchComparison,
    BatchDetailResponse,
    BatchListResponse,
    CheckBatch,
    SiteBaseline,
)
from .repositories.sqlite_history import SqliteHistoryRepository
from .renderers.csv_report import CsvReportRenderer
from .renderers.html_report import HtmlReportRenderer
from .schemas import (
    BatchCreateRequest,
    BaselineRequest,
    CheckRequest,
    DeviceConfig,
    ErrorResponse,
    SiteConfig,
)
from .services.batch_service import BatchAlreadyRunningError, BatchService
from .ports.history import (
    BatchIsBaselineError,
    BatchNotDeletableError,
    BatchNotFoundError,
)
from .services.batch_service import BatchAlreadyRunningError, BatchService
from .services.comparison_service import (
    BaselineRequiresConfirmationError,
    ComparisonService,
)
from .services.report_service import ReportService, UnsupportedReportFormatError
from .site_store import SiteStore


ROOT = Path(__file__).resolve().parents[2]
store = SiteStore(ROOT / "data")
check_service = CheckService()
history = SqliteHistoryRepository(
    Path(
        os.environ.get(
            "MODBUS_HISTORY_DB",
            str(ROOT / "backend" / "data" / "modbus_history.db"),
        )
    )
)
comparison_service = ComparisonService(history)
batch_service = BatchService(
    history,
    check_service.adapter,
    comparison=comparison_service,
)
report_service = ReportService(
    history,
    comparison_service,
    {"csv": CsvReportRenderer(), "html": HtmlReportRenderer()},
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    history.initialize()
    history.fail_interrupted_batches()
    try:
        yield
    finally:
        batch_service.shutdown()
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
def get_site(site_name: str | None = None) -> SiteConfig:
    return store.load(site_name)


@app.get("/api/sites", response_model=list[str])
def list_sites() -> list[str]:
    return store.list_sites()


@app.post("/api/site/save", response_model=SiteConfig)
def save_site(config: SiteConfig) -> SiteConfig:
    return store.save(config)


@app.delete("/api/site/{site_name}", status_code=204)
def delete_site(site_name: str) -> Response:
    if not store.delete(site_name):
        raise HTTPException(status_code=404, detail="site not found")
    return Response(status_code=204)


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


@app.post(
    "/api/check/batches",
    response_model=CheckBatch,
    status_code=202,
)
def create_check_batch(request: BatchCreateRequest) -> CheckBatch:
    try:
        config = store.load(request.site_name)
        if request.site_name and config.site_name != request.site_name:
            raise HTTPException(status_code=404, detail="site not found")
        polling_was_active = check_service.polling_status().active
        if polling_was_active:
            check_service.stop_polling()

        def resume_polling() -> None:
            if polling_was_active and request.resume_polling:
                check_service.start_polling(store.load)

        try:
            return batch_service.start_batch(
                config,
                device_names=request.device_names,
                note=request.note,
                on_complete=resume_polling,
            )
        except Exception:
            if polling_was_active and request.resume_polling:
                check_service.start_polling(store.load)
            raise
    except BatchAlreadyRunningError as error:
        raise HTTPException(status_code=409, detail="a check batch is already running") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/check/batches", response_model=BatchListResponse)
def list_check_batches(
    site_name: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> BatchListResponse:
    items, total = batch_service.list_batches(
        site_name,
        offset=offset,
        limit=limit,
    )
    return BatchListResponse(items=items, total=total)


@app.get("/api/check/batches/{batch_id}", response_model=BatchDetailResponse)
def get_check_batch(batch_id: str) -> BatchDetailResponse:
    try:
        return batch_service.get_batch(batch_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="batch not found") from error


@app.delete("/api/check/batches/{batch_id}", status_code=204)
def delete_check_batch(batch_id: str) -> Response:
    try:
        batch_service.delete_batch(batch_id)
    except BatchNotFoundError as error:
        raise HTTPException(status_code=404, detail="batch not found") from error
    except (BatchIsBaselineError, BatchNotDeletableError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(status_code=204)


@app.post("/api/check/batches/{batch_id}/cancel", response_model=CheckBatch)
def cancel_check_batch(batch_id: str) -> CheckBatch:
    try:
        batch = history.get_batch(batch_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="batch not found") from error
    if batch.status not in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="batch is no longer running")
    if not batch_service.cancel_batch(batch_id):
        raise HTTPException(status_code=409, detail="batch could not be cancelled")
    return history.get_batch(batch_id)


@app.get("/api/sites/{site_name}/baseline", response_model=SiteBaseline)
def get_site_baseline(site_name: str) -> SiteBaseline:
    baseline = history.get_baseline(site_name)
    if baseline is None:
        raise HTTPException(status_code=404, detail="baseline not found")
    return baseline


@app.put("/api/sites/{site_name}/baseline", response_model=SiteBaseline)
def set_site_baseline(site_name: str, request: BaselineRequest) -> SiteBaseline:
    try:
        return comparison_service.set_baseline(
            site_name,
            request.batch_id,
            force=request.force,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail="batch not found") from error
    except BaselineRequiresConfirmationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/sites/{site_name}/baseline", status_code=204)
def clear_site_baseline(site_name: str) -> Response:
    if not history.clear_baseline(site_name):
        raise HTTPException(status_code=404, detail="baseline not found")
    return Response(status_code=204)


@app.get("/api/check/batches/{batch_id}/comparison", response_model=BatchComparison)
def compare_check_batch(batch_id: str) -> BatchComparison:
    try:
        return comparison_service.compare(batch_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="batch not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/check/batches/{batch_id}/report")
def download_check_batch_report(
    batch_id: str,
    report_format: str = Query(alias="format", pattern="^(csv|html)$"),
) -> Response:
    try:
        report = report_service.render(batch_id, report_format)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="batch not found") from error
    except UnsupportedReportFormatError as error:
        raise HTTPException(status_code=422, detail="unsupported report format") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    disposition = f"attachment; filename*=UTF-8''{quote(report.filename)}"
    return Response(
        content=report.content,
        media_type=report.content_type,
        headers={"Content-Disposition": disposition},
    )


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
