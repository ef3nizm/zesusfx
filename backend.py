import os
import shutil
import asyncio
import time
from pathlib import Path

from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from gradio_client import Client, handle_file

# Directories
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "separated"
MIDI_DIR = BASE_DIR / "midi_output"
YT_DIR = BASE_DIR / "youtube_downloads"

for d in [UPLOAD_DIR, OUTPUT_DIR, MIDI_DIR, YT_DIR]:
    d.mkdir(exist_ok=True)

async def auto_cleanup():
    """Cleans up the temporary directories every 5 minutes."""
    while True:
        await asyncio.sleep(5*60)
        for directory in [UPLOAD_DIR, OUTPUT_DIR, MIDI_DIR, YT_DIR]:
            if not directory.exists():
                continue
            for item in directory.iterdir():
                try:
                    if item.is_file() or item.is_symlink():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                except Exception as e:
                    pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start cleanup task
    cleanup_task = asyncio.create_task(auto_cleanup())
    yield
    # Cancel cleanup task on shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="ZESU AI Studio", lifespan=lifespan)

# =============================================
#  VOCAL SEPARATION API
# =============================================

@app.post("/api/separate")
async def separate_audio(file: UploadFile = File(...)):
    import tempfile
    
    # Create a temporary directory for processing
    with tempfile.TemporaryDirectory() as temp_dir_path:
        temp_dir = Path(temp_dir_path)
        file_path = temp_dir / file.filename
        
        try:
            # Save the upload temporarily
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            base_name = file_path.stem
            # We still need a place to serve from, but we'll use OUTPUT_DIR and 
            # ideally clean it up or use a more transient approach.
            # For now, let's keep serving from OUTPUT_DIR but focus on NOT keeping the raw uploads.
            
            output_folder = OUTPUT_DIR / f"{base_name}_{int(time.time())}"
            output_folder.mkdir(exist_ok=True)

            client = Client("abidlabs/music-separation")
            result = await asyncio.to_thread(
                client.predict,
                handle_file(str(file_path)),
                api_name="/predict"
            )

            vocals_src = Path(result[0])
            acc_src = Path(result[1])

            vocals_dst = output_folder / "vocals.wav"
            inst_dst = output_folder / "instrumental.wav"

            shutil.copyfile(vocals_src, vocals_dst)
            shutil.copyfile(acc_src, inst_dst)

            return {
                "status": "success",
                "vocals_url": f"/api/download/sep/{output_folder.name}/vocals.wav",
                "instrumental_url": f"/api/download/sep/{output_folder.name}/instrumental.wav"
            }
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
        # temp_dir is cleaned up automatically here, deleting the original upload

@app.get("/api/download/sep/{folder}/{filename}")
async def download_sep_file(folder: str, filename: str):
    path = OUTPUT_DIR / folder / filename
    if path.exists():
        return FileResponse(path=str(path), filename=filename)
    return JSONResponse(status_code=404, content={"error": "Not Found"})

# =============================================
#  MIDI DOWNLOAD API
# =============================================

@app.get("/api/download-midi/{folder}/{filename}")
async def download_midi(folder: str, filename: str):
    path = MIDI_DIR / folder / filename
    if path.exists():
        return FileResponse(path=str(path), filename=filename)
    return JSONResponse(status_code=404, content={"error": "Not Found"})

# =============================================
#  YOUTUBE -> MP3 API (Robust Local)
# =============================================

@app.post("/api/youtube")
async def download_youtube(data: dict):
    url = data.get("url")
    if not url:
        return JSONResponse(status_code=400, content={"error": "URL is required"})
    
    try:
        import yt_dlp
        
        # Create a unique folder for this download
        folder_name = f"yt_{int(time.time())}"
        output_path = YT_DIR / folder_name
        output_path.mkdir(exist_ok=True)
        
        # Use a more specific template and options
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(output_path / 'audio.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'add_header': [
                'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language: en-us,en;q=0.5',
            ]
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=True)
            title = info.get('title', 'YouTube Audio')
            
            # Find the actual mp3 file (we named it audio.mp3 via outtmpl + replacement)
            mp3_path = output_path / "audio.mp3"
            if not mp3_path.exists():
                # Fallback check if it kept the original name despite outtmpl (some versions do)
                files = list(output_path.glob("*.mp3"))
                if files: mp3_path = files[0]
                else: raise Exception("File conversion failed.")
            
            # Rename to a nice name for download if possible
            safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '.', '_', '-')]).strip()
            final_name = f"{safe_title}.mp3"
            final_path = output_path / final_name
            os.rename(mp3_path, final_path)
            
            
        return {
            "status": "success",
            "title": title,
            "download_url": f"/api/download/yt/{folder_name}/{final_name}"
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Server error during extraction. Please check the URL."})

@app.get("/api/download/yt/{folder}/{filename}")
async def download_yt_file(folder: str, filename: str):
    path = YT_DIR / folder / filename
    if path.exists():
        return FileResponse(path=str(path), filename=filename)
    return JSONResponse(status_code=404, content={"error": "File not found"})

# =============================================
#  PAGES
# =============================================

@app.get("/")
async def serve_index():
    return HTMLResponse(content=(BASE_DIR / "index.html").read_text(encoding="utf-8"))

@app.get("/midi.html")
async def serve_midi():
    return HTMLResponse(content=(BASE_DIR / "midi.html").read_text(encoding="utf-8"))

@app.get("/youtube.html")
async def serve_youtube():
    return HTMLResponse(content=(BASE_DIR / "youtube.html").read_text(encoding="utf-8"))

app.mount("/", StaticFiles(directory=str(BASE_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
