#!/usr/bin/env python3
"""
Video Clipper Script - Optimized for Android Client
Downloads and processes videos for carousel creation
"""

import subprocess
import os
import sys
from datetime import datetime
from pathlib import Path

def run_command(cmd_list, description=""):
    """Run a command and handle errors gracefully"""
    print(f"🔧 {description}")
    print(f"📋 Command: {' '.join(cmd_list)}")
    
    try:
        result = subprocess.run(cmd_list, check=True, capture_output=True, text=True)
        if result.stdout:
            print(f"✅ Output: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: Command failed with exit code {e.returncode}")
        print(f"📋 Failed command: {' '.join(e.cmd)}")
        if e.stderr:
            print(f"💥 Error details: {e.stderr.strip()}")
        if e.stdout:
            print(f"📝 Output before failure: {e.stdout.strip()}")
        return False

def setup_directories():
    """Create necessary directories"""
    today = datetime.now().strftime('%Y-%m-%d')
    output_dir = Path(f"carousels/{today}-veo-interview")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Created output directory: {output_dir}")
    return output_dir

def check_cookies():
    """Check if YouTube cookies are available"""
    cookies_file = Path.home() / ".config" / "yt-dlp" / "cookies.txt"
    if cookies_file.exists():
        print("🍪 YouTube cookies found - will try with and without")
        return str(cookies_file)
    else:
        print("⚠️ No YouTube cookies found - using Android client (should work)")
        return None

def download_video(video_url, output_path, cookies_file=None):
    """Download video using the best working strategy"""
    
    # Strategy 1: Android client (WORKS!) - try without cookies first
    print("🔄 Strategy 1: Android client (no cookies) - RECOMMENDED")
    cmd1 = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=android",
        "--merge-output-format", "mp4",
        "-f", "best[height<=720]/best",
        "-o", str(output_path),
        video_url
    ]
    if run_command(cmd1, "Android client without cookies"):
        return True
    
    # Strategy 2: Android client with cookies (if available)
    if cookies_file:
        print("🔄 Strategy 2: Android client with cookies")
        cmd2 = [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=android",
            "--merge-output-format", "mp4",
            "-f", "best[height<=720]/best",
            "--cookies", cookies_file,
            "-o", str(output_path),
            video_url
        ]
        if run_command(cmd2, "Android client with cookies"):
            return True
    
    # Strategy 3: MediaConnect client
    print("🔄 Strategy 3: MediaConnect client")
    cmd3 = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=mediaconnect",
        "--merge-output-format", "mp4",
        "-f", "best[height<=720]/best",
        "-o", str(output_path),
        video_url
    ]
    if run_command(cmd3, "MediaConnect client"):
        return True
    
    # Strategy 4: Basic download with specific format
    print("🔄 Strategy 4: Basic download (format 18)")
    cmd4 = [
        "yt-dlp",
        "--merge-output-format", "mp4",
        "-f", "18",  # Standard MP4 360p format
        "-o", str(output_path),
        video_url
    ]
    if run_command(cmd4, "Basic download format 18"):
        return True
    
    # Strategy 5: Any available format
    print("🔄 Strategy 5: Any available format")
    cmd5 = [
        "yt-dlp",
        "-f", "best/worst",
        "-o", str(output_path),
        video_url
    ]
    if run_command(cmd5, "Any available format"):
        return True
    
    return False

def process_video(input_path, output_dir):
    """Process the downloaded video"""
    if not input_path.exists():
        print(f"❌ Input video not found: {input_path}")
        return False
    
    print(f"🎬 Processing video: {input_path}")
    
    # Get video info first
    info_cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(input_path)
    ]
    
    if run_command(info_cmd, "Getting video information"):
        print("✅ Video file is valid")
    
    # Create a 30-second clip
    clip_path = output_dir / "veo_street_A_clip.mp4"
    
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-t", "30",  # First 30 seconds
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        "-crf", "23",
        "-y",  # Overwrite output file
        str(clip_path)
    ]
    
    success = run_command(cmd, "Creating 30-second clip")
    
    if success:
        print(f"✅ Clip created: {clip_path}")
    
    return success

def main():
    """Main execution function"""
    print("🚀 Starting Video Clipper Script (Android Client Optimized)")
    print("=" * 60)
    
    # Setup
    output_dir = setup_directories()
    cookies_file = check_cookies()
    
    # Configuration
    video_url = "https://youtu.be/Tvz8an1znIo"
    raw_video_path = output_dir / "veo_street_A_raw.mp4"
    
    print(f"🎯 Target video: {video_url}")
    print(f"📁 Output directory: {output_dir}")
    
    # Download video
    print("\n" + "=" * 60)
    print("📥 DOWNLOADING VIDEO")
    print("=" * 60)
    
    if not download_video(video_url, raw_video_path, cookies_file):
        print("❌ All download attempts failed!")
        print("\n🔧 TROUBLESHOOTING:")
        print("1. Check if video is accessible: https://youtu.be/Tvz8an1znIo")
        print("2. Try updating yt-dlp: pip install -U yt-dlp")
        print("3. Check network connection")
        sys.exit(1)
    
    # Verify download
    if not raw_video_path.exists():
        print(f"❌ Downloaded video not found at: {raw_video_path}")
        sys.exit(1)
    
    file_size = raw_video_path.stat().st_size / (1024 * 1024)  # MB
    print(f"✅ Video downloaded successfully ({file_size:.1f} MB)")
    
    # Process video
    print("\n" + "=" * 60)
    print("🎬 PROCESSING VIDEO")
    print("=" * 60)
    
    if not process_video(raw_video_path, output_dir):
        print("❌ Failed to process video")
        sys.exit(1)
    
    # List created files
    print("\n" + "=" * 60)
    print("📋 CREATED FILES")
    print("=" * 60)
    
    for file_path in output_dir.iterdir():
        if file_path.is_file():
            size = file_path.stat().st_size / (1024 * 1024)  # MB
            print(f"📄 {file_path.name} ({size:.1f} MB)")
    
    print("\n✅ Video clipper completed successfully!")
    print("🎉 Android client method worked as expected!")

if __name__ == "__main__":
    main()