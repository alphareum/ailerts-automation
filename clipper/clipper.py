#!/usr/bin/env python3
import csv, subprocess, datetime, pathlib

########################
# Paths & helper setup #
########################
ROOT     = pathlib.Path(__file__).resolve().parents[1]
CSV      = ROOT / "clipper" / "feeds_to_clips.csv"
today    = datetime.date.today().isoformat()
OUT_DIR  = ROOT / f"carousels/{today}-veo-interview"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def run(cmd_list):
    print(">", " ".join(map(str, cmd_list)))
    subprocess.run(cmd_list, check=True)

def seconds(t):          # "HH:MM:SS" → int seconds
    h, m, s = map(int, t.split(":"))
    return h*3600 + m*60 + s

################
# Main loop    #
################
for row in csv.DictReader(CSV.open()):
    slug = row["slug"]
    raw  = OUT_DIR / f"{slug}_raw.mp4"  # temp file
    sq   = OUT_DIR / f"{slug}.mp4"      # final square clip

    # 1. Download & merge to MP4
    run([
        "yt-dlp",
        "--merge-output-format", "mp4",
        "-f", "bestvideo*+bestaudio/best",   # smart fallback
        "-o", str(raw),
        row["url"],
    ])

    # 2. Trim & square-crop
    dur = seconds(row["end"]) - seconds(row["start"])
    run([
        "ffmpeg", "-y",
        "-i",  str(raw),
        "-ss", row["start"], "-t", str(dur),
        "-vf", "crop='min(in_w\\,in_h)':'min(in_w\\,in_h)',"
               "scale=1080:1080,setsar=1",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        str(sq),
    ])
    raw.unlink()         # keep folder tidy

print("✅ Clips saved to", OUT_DIR)

