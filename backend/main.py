import asyncio
import io
import json
import os
import tempfile
import uuid
from typing import Any, Dict, List
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pipeline import get_expected_columns, process_single_row

app = FastAPI(title="Product Catalog Enrichment API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: Dict[str, Dict[str, Any]] = {}
# Safe OS temporary directory: Deployment & Production Safe
JOBS_DIR = os.path.join(tempfile.gettempdir(), "specs_catalog_jobs")
os.makedirs(JOBS_DIR, exist_ok=True)


def _read_upload_to_records(filename: str, content: bytes) -> List[Dict[str, Any]]:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    buffer = io.BytesIO(content)
    df = pd.read_excel(buffer) if ext in ("xlsx", "xls") else pd.read_csv(buffer)
    df = df.where(pd.notnull(df), "")
    return df.to_dict(orient="records")


@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    content = await file.read()
    records = _read_upload_to_records(file.filename or "upload", content)
    if not records:
        raise HTTPException(status_code=400, detail="The uploaded file has no data rows.")

    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "filename": file.filename,
        "rows": records,
        "total": len(records),
        "status": "uploaded",
        "results": [],
        "output_path": None,
    }
    return {
        "job_id": job_id,
        "filename": file.filename,
        "total_rows": len(records),
        "columns": list(records[0].keys()),
    }


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@app.get("/api/process/{job_id}")
async def process_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    async def event_stream():
        if job["status"] == "done":
            yield _sse("done", {
                "job_id": job_id,
                "download_url": f"/api/download/{job_id}",
                "succeeded": sum(1 for r in job["results"] if r["status"] == "success"),
                "failed": sum(1 for r in job["results"] if r["status"] != "success"),
            })
            return

        job["status"] = "processing"
        total = job["total"]
        csv_rows = []

        yield _sse("start", {"job_id": job_id, "total": total, "filename": job["filename"]})

        for index, row in enumerate(job["rows"], start=1):
            result = await asyncio.to_thread(process_single_row, row)
            job["results"].append(result)
            if result["status"] == "success" and result.get("csv_row"):
                csv_rows.append(result["csv_row"])

            yield _sse("progress", {
                "index": index,
                "total": total,
                "brand": result["brand"],
                "part_num": result["part_num"],
                "product_name": result["product_name"],
                "status": result["status"],
                "error": result["error"],
                "sources_found": result["sources_found"],
                "anomalies": result["anomalies"],
                "citations": result["citations"],
            })
            await asyncio.sleep(0.05)

        final_df = pd.DataFrame(csv_rows)
        columns = get_expected_columns()
        if columns:
            for col in columns:
                if col not in final_df.columns:
                    final_df[col] = ""
            final_df = final_df[columns]

        output_path = os.path.join(JOBS_DIR, f"{job_id}.csv")
        final_df.to_csv(output_path, index=False)
        job["output_path"] = output_path
        job["status"] = "done"

        succeeded = sum(1 for r in job["results"] if r["status"] == "success")
        yield _sse("done", {
            "job_id": job_id,
            "download_url": f"/api/download/{job_id}",
            "succeeded": succeeded,
            "failed": total - succeeded,
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/download/{job_id}")
async def download_job(job_id: str):
    job = JOBS.get(job_id)
    if not job or not job.get("output_path"):
        raise HTTPException(status_code=404, detail="Result file not ready yet.")
    return FileResponse(job["output_path"], media_type="text/csv", filename=f"enriched_catalog_{job_id}.csv")