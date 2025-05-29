#!/usr/bin/env python3
"""
Video Clipper Script
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
        print("🍪 YouTube cookies found - using authenticated download")
        return str(cookies_file)
    else:
        print("⚠️ No YouTube cookies found - attempting anonymous download")
        return None

def download_video(video_url, output_path, cookies_file=None):
    """Download video from YouTube"""
    cmd = [
        "yt-dlp",
        "--merge-output-format", "mp4",
        "-f", "bestvideo*+bestaudio/best",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "--add-header", "Accept-Language:en-US,en;q=0.9",
        "--extractor-args", "youtube:player_client=web",
        "-o", str(output_path),
    ]
    
    # Add cookies if available
    if cookies_file:
        cmd.extend(["--cookies", cookies_file])
    
    cmd.append(video_url)
    
    success = run_command(cmd, f"Downloading video from {video_url}")
    
    if not success:
        print("🔄 Retrying with different settings...")
        # Retry with ios client
        retry_cmd = cmd.copy()
        # Replace web client with ios
        for i, arg in enumerate(retry_cmd):
            if arg == "youtube:player_client=web":
                retry_cmd[i] = "youtube:player_client=ios"
                break
        
        success = run_command(retry_cmd, "Retrying download with iOS client")
    
    return success

def process_video(input_path, output_dir):
    """Process the downloaded video (add your video processing logic here)"""
    if not input_path.exists():
        print(f"❌ Input video not found: {input_path}")
        return False
    
    print(f"🎬 Processing video: {input_path}")
    
    # Example: Create a 30-second clip from the beginning
    clip_path = output_dir / "veo_street_A_clip.mp4"
    
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-t", "30",  # First 30 seconds
        "-c:v", "libx264",
        "-c:a", "aac",
        "-y",  # Overwrite output file
        str(clip_path)
    ]
    
    success = run_command(cmd, "Creating 30-second clip")
    
    if success:
        print(f"✅ Clip created: {clip_path}")
        
        # Get video info
        info_cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(clip_path)
        ]
        
        run_command(info_cmd, "Getting video information")
    
    return success

def main():
    """Main execution function"""
    print("🚀 Starting Video Clipper Script")
    print("=" * 50)
    
    # Setup
    output_dir = setup_directories()
    cookies_file = check_cookies()
    
    # Configuration
    video_url = "https://youtu.be/Tvz8an1znIo"
    raw_video_path = output_dir / "veo_street_A_raw.mp4"
    
    print(f"🎯 Target video: {video_url}")
    print(f"📁 Output directory: {output_dir}")
    
    # Download video
    print("\n" + "=" * 50)
    print("📥 DOWNLOADING VIDEO")
    print("=" * 50)
    
    if not download_video(video_url, raw_video_path, cookies_file):
        print("❌ Failed to download video. Please check:")
        print("   1. YouTube cookies are properly configured")
        print("   2. Video URL is accessible")
        print("   3. Network connection is stable")
        sys.exit(1)
    
    # Verify download
    if not raw_video_path.exists():
        print(f"❌ Downloaded video not found at: {raw_video_path}")
        sys.exit(1)
    
    file_size = raw_video_path.stat().st_size / (1024 * 1024)  # MB
    print(f"✅ Video downloaded successfully ({file_size:.1f} MB)")
    
    # Process video
    print("\n" + "=" * 50)
    print("🎬 PROCESSING VIDEO")
    print("=" * 50)
    
    if not process_video(raw_video_path, output_dir):
        print("❌ Failed to process video")
        sys.exit(1)
    
    # List created files
    print("\n" + "=" * 50)
    print("📋 CREATED FILES")
    print("=" * 50)
    
    for file_path in output_dir.iterdir():
        if file_path.is_file():
            size = file_path.stat().st_size / (1024 * 1024)  # MB
            print(f"📄 {file_path.name} ({size:.1f} MB)")
    
    print("\n✅ Video clipper completed successfully!")

if __name__ == "__main__":
    main()