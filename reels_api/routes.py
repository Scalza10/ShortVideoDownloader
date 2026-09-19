import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse

from reels_api import media
from reels_api.auth import has_access, require_access, share_key_matches, unauthorized
from reels_api.downloader import ytdlp_version
from reels_api.models import CreateJobRequest, Job, JobStatus, job_to_dict

router = APIRouter()
protected = APIRouter(dependencies=[Depends(require_access)])


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60].strip("-") or "video"


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"error": "not_found", "message": "Unknown or expired job."})


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "ytdlp_version": ytdlp_version(), "ffmpeg": media.ffmpeg_available()}


@protected.post("/jobs", status_code=202)
async def create_job(body: CreateJobRequest, request: Request) -> dict:
    """The first job's id and status as before; ids lists one job per video of the post (X links spec 6)."""
    jobs = await request.app.state.manager.submit(body.url)
    first = jobs[0]
    return {"id": first.id, "status": first.status.value, "ids": [job.id for job in jobs]}


@protected.get("/jobs")
async def list_jobs(request: Request) -> dict:
    jobs = await request.app.state.store.list_recent()
    base = request.app.state.settings.public_base_url
    return {"jobs": [job_to_dict(job, base) for job in jobs]}


@protected.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict:
    job = await request.app.state.store.get(job_id)
    if job is None:
        raise _not_found()
    return job_to_dict(job, request.app.state.settings.public_base_url)


async def _file_job(request: Request, job_id: str, k: str | None, x_api_key: str | None) -> Job:
    """The done job behind /files/, once the API key, the cookie or its share key allows it (links spec 5.2)."""
    job = await request.app.state.store.get(job_id)
    if not has_access(request, x_api_key) and not share_key_matches(job, k):
        raise unauthorized()
    if job is None or job.status != JobStatus.DONE or job.result is None:
        raise _not_found()
    return job


@router.get("/files/{job_id}.mp4")
async def get_file(
    job_id: str, request: Request, k: str | None = None, x_api_key: str | None = Header(default=None)
) -> FileResponse:
    job = await _file_job(request, job_id, k, x_api_key)
    if not job.result.file_path.is_file():
        raise _not_found()
    return FileResponse(
        job.result.file_path,
        media_type="video/mp4",
        filename=f"{slugify(job.result.title)}.mp4",
    )


@router.get("/files/{job_id}.jpg")
async def get_thumbnail(
    job_id: str, request: Request, k: str | None = None, x_api_key: str | None = Header(default=None)
) -> FileResponse:
    job = await _file_job(request, job_id, k, x_api_key)
    thumb = job.result.thumbnail_path
    if thumb is None or not thumb.is_file():
        raise _not_found()
    return FileResponse(
        thumb,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=21600"},
    )


router.include_router(protected)
