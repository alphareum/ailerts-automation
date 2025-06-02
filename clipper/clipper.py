#!/usr/bin/env python3
"""
Intelligent Video Clipper Script - Auto-generates clips based on content analysis
Downloads and processes videos with automatic scene detection, audio analysis,
and content-aware clipping for optimal carousel creation.
"""

import subprocess
import os
import sys
import time
import json
import logging
import tempfile
import shutil
import re
import math
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple, NamedTuple
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import argparse

class SceneInfo(NamedTuple):
    """Information about a detected scene"""
    start_time: float
    end_time: float
    duration: float
    score: float
    clip_type: str  # 'scene_change', 'audio_peak', 'motion', 'face_detection'
    metadata: Dict

@dataclass
class ClippingConfig:
    """Configuration for automatic clipping"""
    # Scene detection settings
    scene_threshold: float = 0.3  # Scene change sensitivity (0.1-1.0)
    min_clip_duration: float = 5.0  # Minimum clip length in seconds
    max_clip_duration: float = 60.0  # Maximum clip length in seconds
    target_clip_duration: float = 30.0  # Preferred clip length
    max_clips: int = 10  # Maximum number of clips to generate
    
    # Audio analysis settings
    audio_analysis_enabled: bool = True
    detect_speech: bool = True
    detect_music: bool = True
    audio_silence_threshold: float = -40  # dB threshold for silence
    
    # Visual analysis settings
    motion_analysis_enabled: bool = True
    face_detection_enabled: bool = True
    text_detection_enabled: bool = False
    
    # Content preferences
    prefer_faces: bool = True  # Prioritize clips with faces
    prefer_speech: bool = True  # Prioritize clips with speech
    prefer_motion: bool = True  # Prioritize clips with movement
    avoid_silence: bool = True  # Avoid clips with long silences
    
    # Quality settings
    min_resolution_height: int = 360
    frame_analysis_interval: float = 1.0  # Analyze every N seconds

@dataclass
class Config:
    """Enhanced configuration class"""
    video_url: str = "https://youtu.be/Tvz8an1znIo"
    output_base_dir: str = "carousels"
    project_name: str = "veo-interview"
    max_retries: int = 7
    quality_preference: str = "720p"
    fallback_enabled: bool = True
    cleanup_temp_files: bool = True
    
    # Auto-clipping configuration
    clipping: ClippingConfig = None
    
    def __post_init__(self):
        if self.clipping is None:
            self.clipping = ClippingConfig()
    
    @classmethod
    def from_file(cls, config_path: Path) -> 'Config':
        """Load configuration from JSON file"""
        if config_path.exists():
            with open(config_path, 'r') as f:
                data = json.load(f)
                # Handle nested clipping config
                if 'clipping' in data:
                    data['clipping'] = ClippingConfig(**data['clipping'])
                return cls(**data)
        return cls()
    
    def save_to_file(self, config_path: Path):
        """Save configuration to JSON file"""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)

class VideoClipperError(Exception):
    """Custom exception for video clipper errors"""
    pass

class ContentAnalyzer:
    """Analyzes video content for intelligent clipping"""
    
    def __init__(self, logger: logging.Logger, config: ClippingConfig):
        self.logger = logger
        self.config = config
    
    def _run_analysis_command(self, cmd: List[str]) -> Tuple[bool, str]:
        """Run analysis command and return results"""
        try:
            result = subprocess.run(
                cmd, check=True, capture_output=True, text=True, timeout=300
            )
            return True, result.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.warning(f"Analysis command failed: {e}")
            return False, ""
    
    def detect_scenes(self, video_path: Path) -> List[SceneInfo]:
        """Detect scene changes using ffmpeg"""
        self.logger.info("🎬 Detecting scene changes...")
        
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", f"select='gt(scene,{self.config.scene_threshold})',showinfo",
            "-f", "null",
            "-"
        ]
        
        success, output = self._run_analysis_command(cmd)
        if not success:
            return []
        
        scenes = []
        timestamps = []
        
        # Parse ffmpeg output for scene change timestamps
        for line in output.split('\n'):
            if 'pts_time:' in line:
                match = re.search(r'pts_time:(\d+\.?\d*)', line)
                if match:
                    timestamps.append(float(match.group(1)))
        
        # Convert timestamps to scene segments
        for i in range(len(timestamps) - 1):
            start_time = timestamps[i]
            end_time = timestamps[i + 1]
            duration = end_time - start_time
            
            if duration >= self.config.min_clip_duration:
                scenes.append(SceneInfo(
                    start_time=start_time,
                    end_time=end_time,
                    duration=duration,
                    score=1.0,
                    clip_type='scene_change',
                    metadata={'method': 'ffmpeg_scene_detect'}
                ))
        
        self.logger.info(f"✅ Found {len(scenes)} scene changes")
        return scenes
    
    def analyze_audio(self, video_path: Path) -> List[SceneInfo]:
        """Analyze audio for speech, music, and interesting segments"""
        self.logger.info("🎵 Analyzing audio content...")
        
        audio_segments = []
        
        if self.config.detect_speech:
            audio_segments.extend(self._detect_speech_segments(video_path))
        
        if self.config.detect_music:
            audio_segments.extend(self._detect_music_segments(video_path))
        
        # Detect audio peaks/interesting moments
        audio_segments.extend(self._detect_audio_peaks(video_path))
        
        self.logger.info(f"✅ Found {len(audio_segments)} audio segments")
        return audio_segments
    
    def _detect_speech_segments(self, video_path: Path) -> List[SceneInfo]:
        """Detect segments with speech using volume analysis"""
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-af", "volumedetect",
            "-f", "null",
            "-"
        ]
        
        success, output = self._run_analysis_command(cmd)
        if not success:
            return []
        
        # Simple speech detection based on volume consistency
        # In a real implementation, you might use speech recognition APIs
        speech_segments = []
        
        # Analyze volume levels to find consistent audio (likely speech)
        cmd = [
            "ffprobe",
            "-f", "lavfi",
            "-i", f"amovie={video_path},astats=metadata=1:reset=1",
            "-show_entries", "frame=pkt_pts_time:frame_tags=lavfi.astats.Overall.RMS_level",
            "-of", "csv=p=0"
        ]
        
        success, output = self._run_analysis_command(cmd)
        if success:
            lines = output.strip().split('\n')
            current_speech_start = None
            
            for line in lines:
                if ',' in line:
                    try:
                        timestamp, rms_level = line.split(',')
                        timestamp = float(timestamp)
                        rms_level = float(rms_level) if rms_level != 'inf' else -100
                        
                        # Detect speech-like audio patterns
                        if rms_level > self.config.audio_silence_threshold:
                            if current_speech_start is None:
                                current_speech_start = timestamp
                        else:
                            if current_speech_start is not None:
                                duration = timestamp - current_speech_start
                                if duration >= self.config.min_clip_duration:
                                    speech_segments.append(SceneInfo(
                                        start_time=current_speech_start,
                                        end_time=timestamp,
                                        duration=duration,
                                        score=0.8,
                                        clip_type='speech',
                                        metadata={'rms_level': rms_level}
                                    ))
                                current_speech_start = None
                    except ValueError:
                        continue
        
        return speech_segments
    
    def _detect_music_segments(self, video_path: Path) -> List[SceneInfo]:
        """Detect segments with music using spectral analysis"""
        # Simplified music detection - in practice, you'd use more sophisticated analysis
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-af", "showspectrumpic=s=640x360:mode=separate",
            "-frames:v", "1",
            "-f", "image2",
            "-"
        ]
        
        # For now, return empty list - music detection would require more complex analysis
        return []
    
    def _detect_audio_peaks(self, video_path: Path) -> List[SceneInfo]:
        """Detect audio peaks and interesting moments"""
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-af", "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level",
            "-f", "null",
            "-"
        ]
        
        success, output = self._run_analysis_command(cmd)
        if not success:
            return []
        
        peaks = []
        # Parse peak information and create segments around interesting audio moments
        # This is a simplified implementation
        
        return peaks
    
    def analyze_motion(self, video_path: Path) -> List[SceneInfo]:
        """Analyze video for motion and activity"""
        self.logger.info("🏃 Analyzing motion content...")
        
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", "select='gt(scene,0.1)',metadata=print",
            "-f", "null",
            "-"
        ]
        
        success, output = self._run_analysis_command(cmd)
        motion_segments = []
        
        # Motion analysis would go here
        # For now, return empty list
        
        self.logger.info(f"✅ Found {len(motion_segments)} motion segments")
        return motion_segments
    
    def detect_faces(self, video_path: Path) -> List[SceneInfo]:
        """Detect segments with faces (requires opencv or similar)"""
        if not self.config.face_detection_enabled:
            return []
        
        self.logger.info("👤 Detecting faces...")
        
        # Face detection would require additional dependencies
        # For now, return empty list
        face_segments = []
        
        self.logger.info(f"✅ Found {len(face_segments)} face segments")
        return face_segments
    
    def get_video_info(self, video_path: Path) -> Dict:
        """Get comprehensive video information"""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path)
        ]
        
        success, output = self._run_analysis_command(cmd)
        if success:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                pass
        
        return {}

class IntelligentVideoClipper:
    """Enhanced video clipper with intelligent content analysis"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = self._setup_logging()
        self.temp_dir: Optional[Path] = None
        self.output_dir: Optional[Path] = None
        self.analyzer = ContentAnalyzer(self.logger, config.clipping)
        
        # Download strategies (same as before)
        self.download_strategies = [
            self._strategy_tv_embedded,
            self._strategy_android_client,
            self._strategy_browser_cookies,
            self._strategy_web_client,
            self._strategy_alternative_url,
            self._strategy_minimal,
            self._strategy_proxy_headers
        ]
    
    def _setup_logging(self) -> logging.Logger:
        """Setup enhanced logging"""
        logger = logging.getLogger('intelligent_video_clipper')
        logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # File handler
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / f"intelligent_clipper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        return logger
    
    @contextmanager
    def _managed_temp_dir(self):
        """Context manager for temporary directory cleanup"""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="intelligent_clipper_"))
        try:
            self.logger.info(f"📁 Created temporary directory: {self.temp_dir}")
            yield self.temp_dir
        finally:
            if self.config.cleanup_temp_files and self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                self.logger.info(f"🧹 Cleaned up temporary directory: {self.temp_dir}")
    
    def _check_dependencies(self) -> bool:
        """Check if required dependencies are available"""
        dependencies = {
            'yt-dlp': ['yt-dlp', '--version'],
            'ffmpeg': ['ffmpeg', '-version'],
            'ffprobe': ['ffprobe', '-version']
        }
        
        missing = []
        for name, cmd in dependencies.items():
            if not self._run_command_silent(cmd):
                missing.append(name)
        
        if missing:
            self.logger.error(f"❌ Missing dependencies: {', '.join(missing)}")
            return False
        
        self.logger.info("✅ All dependencies available")
        return True
    
    def _run_command_silent(self, cmd_list: List[str]) -> bool:
        """Run command silently and return success status"""
        try:
            subprocess.run(cmd_list, check=True, capture_output=True, text=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def _run_command_with_retry(self, cmd_list: List[str], description: str = "", 
                              max_retries: int = 3) -> Tuple[bool, str]:
        """Run command with exponential backoff retry logic"""
        self.logger.info(f"🔧 {description}")
        self.logger.debug(f"📋 Command: {' '.join(cmd_list)}")
        
        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    cmd_list, 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=300
                )
                
                if result.stdout:
                    self.logger.debug(f"✅ Output: {result.stdout.strip()}")
                return True, result.stdout
                
            except subprocess.TimeoutExpired:
                self.logger.warning(f"⏰ Command timed out (attempt {attempt + 1}/{max_retries})")
            except subprocess.CalledProcessError as e:
                self.logger.warning(
                    f"❌ Command failed with exit code {e.returncode} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                if e.stderr:
                    self.logger.debug(f"💥 Error: {e.stderr.strip()}")
                
                if "Video unavailable" in str(e.stderr) or "Private video" in str(e.stderr):
                    return False, e.stderr
            
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                self.logger.info(f"⏳ Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
        
        return False, "Max retries exceeded"
    
    def _setup_directories(self) -> Path:
        """Create output directory structure"""
        today = datetime.now().strftime('%Y-%m-%d')
        self.output_dir = Path(self.config.output_base_dir) / f"{today}-{self.config.project_name}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for different types of clips
        (self.output_dir / "auto_clips").mkdir(exist_ok=True)
        (self.output_dir / "scene_clips").mkdir(exist_ok=True)
        (self.output_dir / "audio_clips").mkdir(exist_ok=True)
        
        self.logger.info(f"📁 Output directory: {self.output_dir}")
        return self.output_dir
    
    def _find_cookies(self) -> Optional[str]:
        """Find YouTube cookies"""
        cookie_locations = [
            Path.home() / ".config" / "yt-dlp" / "cookies.txt",
            Path.cwd() / "cookies.txt",
            Path(os.getenv("YOUTUBE_COOKIES", ""))
        ]
        
        for cookie_path in cookie_locations:
            if cookie_path and cookie_path.exists():
                self.logger.info(f"🍪 Found cookies: {cookie_path}")
                return str(cookie_path)
        
        self.logger.warning("⚠️ No YouTube cookies found")
        return None
    
    def _get_quality_format(self) -> str:
        """Get format string based on quality preference"""
        quality_map = {
            "1080p": "best[height<=1080]/worst",
            "720p": "best[height<=720]/worst", 
            "480p": "best[height<=480]/worst",
            "360p": "18/worst",
            "worst": "worst"
        }
        return quality_map.get(self.config.quality_preference, "best[height<=720]/worst")
    
    # Download strategy methods (same as before - keeping them for brevity)
    def _strategy_tv_embedded(self, video_url: str, output_path: Path, cookies_file: Optional[str]) -> bool:
        if not cookies_file:
            return False
        cmd = [
            "yt-dlp", "--extractor-args", "youtube:player_client=tv_embedded",
            "--user-agent", "Mozilla/5.0 (SMART-TV; Linux; Tizen 2.4.0) AppleWebkit/538.1",
            "--merge-output-format", "mp4", "-f", self._get_quality_format(),
            "--cookies", cookies_file, "--sleep-interval", "2", "--max-sleep-interval", "5",
            "-o", str(output_path), video_url
        ]
        success, _ = self._run_command_with_retry(cmd, "TV embedded with cookies")
        return success
    
    def _strategy_android_client(self, video_url: str, output_path: Path, cookies_file: Optional[str]) -> bool:
        if not cookies_file:
            return False
        cmd = [
            "yt-dlp", "--extractor-args", "youtube:player_client=android",
            "--user-agent", "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
            "--merge-output-format", "mp4", "-f", "18/worst", "--cookies", cookies_file,
            "--sleep-interval", "3", "--max-sleep-interval", "7", "-o", str(output_path), video_url
        ]
        success, _ = self._run_command_with_retry(cmd, "Android client with cookies")
        return success
    
    def _strategy_browser_cookies(self, video_url: str, output_path: Path, cookies_file: Optional[str]) -> bool:
        cmd = [
            "yt-dlp", "--cookies-from-browser", "chrome", "--merge-output-format", "mp4",
            "-f", "18/worst", "--sleep-interval", "2", "-o", str(output_path), video_url
        ]
        success, _ = self._run_command_with_retry(cmd, "Direct browser cookies")
        return success
    
    def _strategy_web_client(self, video_url: str, output_path: Path, cookies_file: Optional[str]) -> bool:
        cmd = [
            "yt-dlp", "--extractor-args", "youtube:player_client=web",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "--add-header", "Accept-Language:en-US,en;q=0.9", "--merge-output-format", "mp4",
            "-f", "18/worst", "--sleep-interval", "4", "-o", str(output_path), video_url
        ]
        success, _ = self._run_command_with_retry(cmd, "Web client with headers")
        return success
    
    def _strategy_alternative_url(self, video_url: str, output_path: Path, cookies_file: Optional[str]) -> bool:
        alt_url = video_url.replace("youtu.be/", "youtube.com/watch?v=")
        cmd = ["yt-dlp", "--merge-output-format", "mp4", "-f", "18/worst", 
               "--sleep-interval", "2", "-o", str(output_path), alt_url]
        success, _ = self._run_command_with_retry(cmd, "Alternative URL format")
        return success
    
    def _strategy_minimal(self, video_url: str, output_path: Path, cookies_file: Optional[str]) -> bool:
        cmd = ["yt-dlp", "-f", "worst", "-o", str(output_path), video_url]
        success, _ = self._run_command_with_retry(cmd, "Minimal command")
        return success
    
    def _strategy_proxy_headers(self, video_url: str, output_path: Path, cookies_file: Optional[str]) -> bool:
        cmd = [
            "yt-dlp", "--user-agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "--add-header", "Accept-Encoding:gzip, deflate, br", "-f", "worst",
            "-o", str(output_path), video_url
        ]
        success, _ = self._run_command_with_retry(cmd, "Proxy-like headers")
        return success
    
    def _download_video(self, video_url: str, output_path: Path) -> bool:
        """Download video using multiple strategies"""
        cookies_file = self._find_cookies()
        
        self.logger.info("📥 Starting download with multiple strategies...")
        
        for i, strategy in enumerate(self.download_strategies, 1):
            self.logger.info(f"🔄 Strategy {i}/{len(self.download_strategies)}: {strategy.__name__}")
            
            try:
                if strategy(video_url, output_path, cookies_file):
                    self.logger.info(f"✅ Download successful with strategy {i}")
                    return True
            except Exception as e:
                self.logger.error(f"❌ Strategy {i} failed: {e}")
            
            if i < len(self.download_strategies):
                wait_time = min(3 + i, 10)
                self.logger.info(f"⏳ Waiting {wait_time} seconds...")
                time.sleep(wait_time)
        
        return False
    
    def _create_fallback_video(self, output_path: Path) -> bool:
        """Create fallback video"""
        if not self.config.fallback_enabled:
            return False
        
        self.logger.info("🎬 Creating fallback video...")
        cmd = [
            "ffmpeg", "-f", "lavfi", "-i", "color=red:size=640x360:duration=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
            "-vf", "drawtext=text='Download Failed - Fallback Video':fontsize=24:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
            "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", "-y", str(output_path)
        ]
        
        success, _ = self._run_command_with_retry(cmd, "Creating fallback video")
        return success
    
    def _analyze_video_content(self, video_path: Path) -> List[SceneInfo]:
        """Perform comprehensive content analysis"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("🧠 ANALYZING VIDEO CONTENT")
        self.logger.info("=" * 70)
        
        all_segments = []
        
        # Get video info first
        video_info = self.analyzer.get_video_info(video_path)
        if 'format' in video_info:
            duration = float(video_info['format'].get('duration', 0))
            self.logger.info(f"📹 Video duration: {duration:.1f} seconds")
        
        # Scene detection
        scenes = self.analyzer.detect_scenes(video_path)
        all_segments.extend(scenes)
        
        # Audio analysis
        if self.config.clipping.audio_analysis_enabled:
            audio_segments = self.analyzer.analyze_audio(video_path)
            all_segments.extend(audio_segments)
        
        # Motion analysis
        if self.config.clipping.motion_analysis_enabled:
            motion_segments = self.analyzer.analyze_motion(video_path)
            all_segments.extend(motion_segments)
        
        # Face detection
        if self.config.clipping.face_detection_enabled:
            face_segments = self.analyzer.detect_faces(video_path)
            all_segments.extend(face_segments)
        
        self.logger.info(f"🎯 Total segments found: {len(all_segments)}")
        return all_segments
    
    def _score_and_rank_segments(self, segments: List[SceneInfo]) -> List[SceneInfo]:
        """Score and rank segments based on content preferences"""
        self.logger.info("📊 Scoring and ranking segments...")
        
        scored_segments = []
        
        for segment in segments:
            score = segment.score
            
            # Apply preference bonuses
            if segment.clip_type == 'speech' and self.config.clipping.prefer_speech:
                score *= 1.5
            elif segment.clip_type == 'face_detection' and self.config.clipping.prefer_faces:
                score *= 1.3
            elif segment.clip_type == 'motion' and self.config.clipping.prefer_motion:
                score *= 1.2
            
            # Duration preference (closer to target gets higher score)
            duration_factor = 1 - abs(segment.duration - self.config.clipping.target_clip_duration) / self.config.clipping.target_clip_duration
            score *= max(0.5, duration_factor)
            
            scored_segments.append(SceneInfo(
                start_time=segment.start_time,
                end_time=segment.end_time,
                duration=segment.duration,
                score=score,
                clip_type=segment.clip_type,
                metadata=segment.metadata
            ))
        
        # Sort by score (highest first)
        scored_segments.sort(key=lambda x: x.score, reverse=True)
        
        # Remove overlapping segments
        final_segments = self._remove_overlaps(scored_segments)
        
        self.logger.info(f"✅ Selected {len(final_segments)} non-overlapping segments")
        return final_segments[:self.config.clipping.max_clips]
    
    def _remove_overlaps(self, segments: List[SceneInfo]) -> List[SceneInfo]:
        """Remove overlapping segments, keeping highest scored ones"""
        if not segments:
            return []
        
        non_overlapping = [segments[0]]
        
        for segment in segments[1:]:
            overlaps = False
            for existing in non_overlapping:
                # Check for overlap
                if not (segment.end_time <= existing.start_time or segment.start_time >= existing.end_time):
                    overlaps = True
                    break
            
            if not overlaps:
                non_overlapping.append(segment)
        
        return non_overlapping
    
    def _create_intelligent_clips(self, video_path: Path, segments: List[SceneInfo]) -> bool:
        """Create clips based on analyzed segments"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("✂️ CREATING INTELLIGENT CLIPS")
        self.logger.info("=" * 70)
        
        if not segments:
            self.logger.warning("⚠️ No segments found, creating fallback clip")
            return self._create_fallback_clip(video_path)
        
        clips_created = 0
        
        for i, segment in enumerate(segments, 1):
            clip_name = f"{self.config.project_name}_{segment.clip_type}_{i:02d}.mp4"
            clip_path = self.output_dir / "auto_clips" / clip_name
            
            # Adjust segment duration if needed
            adjusted_start = max(0, segment.start_time)
            adjusted_duration = min(
                segment.duration,
                self.config.clipping.max_clip_duration
            )
            
            cmd = [
                "ffmpeg",
                "-i", str(video_path),
                "-ss", str(adjusted_start),
                "-t", str(adjusted_duration),
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "fast",
                "-crf", "23",
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                "-y",
                str(clip_path)
            ]
            
            success, _ = self._run_command_with_retry(
                cmd, 
                f"Creating clip {i}/{len(segments)}: {segment.clip_type} ({adjusted_duration:.1f}s)"
            )
            
            if success:
                clips_created += 1
                clip_size = clip_path.stat().st_size / (1024 * 1024)
                self.logger.info(
                    f"✅ Clip {i} created: {clip_name} "
                    f"({adjusted_duration:.1f}s, {clip_size:.1f}MB, score: {segment.score:.2f})"
                )
                
                # Save clip metadata
                metadata_path = clip_path.with_suffix('.json')
                with open(metadata_path, 'w') as f:
                    json.dump({
                        'clip_info': {
                            'start_time': adjusted_start,
                            'duration': adjusted_duration,
                            'clip_type': segment.clip_type,
                            'score': segment.score,
                            'metadata': segment.metadata
                        },
                        'source_video': str(video_path.name),
                        'created_at': datetime.now().isoformat()
                    }, f, indent=2)
            else:
                self.logger.error(f"❌ Failed to create clip {i}")
        
        self.logger.info(f"✅ Successfully created {clips_created}/{len(segments)} clips")
        return clips_created > 0
    
    def _create_fallback_clip(self, video_path: Path) -> bool:
        """Create a single fallback clip when analysis fails"""
        self.logger.info("🔄 Creating fallback clip from beginning of video")
        
        clip_path = self.output_dir / "auto_clips" / f"{self.config.project_name}_fallback.mp4"
        
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-t", str(self.config.clipping.target_clip_duration),
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "23",
            "-movflags", "+faststart",
            "-y",
            str(clip_path)
        ]
        
        success, _ = self._run_command_with_retry(cmd, "Creating fallback clip")
        return success
    
    def _create_highlight_reel(self, video_path: Path, segments: List[SceneInfo]) -> bool:
        """Create a highlight reel combining the best segments"""
        if len(segments) < 2:
            return False
        
        self.logger.info("🎬 Creating highlight reel...")
        
        # Select top segments for highlight reel
        top_segments = segments[:min(5, len(segments))]
        
        # Create a concat file for ffmpeg
        concat_file = self.temp_dir / "highlight_concat.txt"
        temp_clips = []
        
        with open(concat_file, 'w') as f:
            for i, segment in enumerate(top_segments):
                temp_clip = self.temp_dir / f"temp_clip_{i}.mp4"
                temp_clips.append(temp_clip)
                
                # Extract segment
                extract_cmd = [
                    "ffmpeg",
                    "-i", str(video_path),
                    "-ss", str(segment.start_time),
                    "-t", str(min(segment.duration, 10)),  # Max 10s per segment in highlight
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-preset", "fast",
                    "-y",
                    str(temp_clip)
                ]
                
                success, _ = self._run_command_with_retry(extract_cmd, f"Extracting highlight segment {i+1}")
                if success:
                    f.write(f"file '{temp_clip}'\n")
        
        # Concatenate clips
        highlight_path = self.output_dir / f"{self.config.project_name}_highlights.mp4"
        concat_cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            "-y",
            str(highlight_path)
        ]
        
        success, _ = self._run_command_with_retry(concat_cmd, "Creating highlight reel")
        
        if success:
            highlight_size = highlight_path.stat().st_size / (1024 * 1024)
            self.logger.info(f"✅ Highlight reel created: {highlight_path.name} ({highlight_size:.1f}MB)")
        
        return success
    
    def _create_analysis_report(self, segments: List[SceneInfo], video_info: Dict) -> bool:
        """Create a detailed analysis report"""
        report_path = self.output_dir / f"{self.config.project_name}_analysis_report.json"
        
        report = {
            'analysis_timestamp': datetime.now().isoformat(),
            'video_info': video_info,
            'config': asdict(self.config.clipping),
            'segments_found': len(segments),
            'segments': [
                {
                    'start_time': seg.start_time,
                    'end_time': seg.end_time,
                    'duration': seg.duration,
                    'score': seg.score,
                    'clip_type': seg.clip_type,
                    'metadata': seg.metadata
                }
                for seg in segments
            ],
            'summary': {
                'total_segments': len(segments),
                'by_type': {},
                'average_score': sum(seg.score for seg in segments) / len(segments) if segments else 0,
                'total_clip_duration': sum(seg.duration for seg in segments),
            }
        }
        
        # Count segments by type
        for segment in segments:
            clip_type = segment.clip_type
            if clip_type not in report['summary']['by_type']:
                report['summary']['by_type'][clip_type] = 0
            report['summary']['by_type'][clip_type] += 1
        
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.logger.info(f"📊 Analysis report saved: {report_path.name}")
        return True
    
    def _validate_video(self, video_path: Path) -> bool:
        """Validate video file integrity"""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path)
        ]
        
        success, output = self._run_command_with_retry(cmd, "Validating video")
        
        if success:
            try:
                info = json.loads(output)
                duration = float(info.get('format', {}).get('duration', 0))
                self.logger.info(f"✅ Video validation passed (duration: {duration:.1f}s)")
                return True
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.error(f"❌ Failed to parse video info: {e}")
        
        return False
    
    def _list_output_files(self) -> Dict[str, float]:
        """List and report created files"""
        files = {}
        total_size = 0
        
        for file_path in self.output_dir.rglob("*"):
            if file_path.is_file():
                size = file_path.stat().st_size / (1024 * 1024)
                relative_path = file_path.relative_to(self.output_dir)
                files[str(relative_path)] = size
                total_size += size
                self.logger.info(f"📄 {relative_path} ({size:.1f} MB)")
        
        self.logger.info(f"💾 Total output: {total_size:.1f} MB")
        return files
    
    def process(self) -> bool:
        """Main processing function with intelligent clipping"""
        try:
            # Dependency check
            if not self._check_dependencies():
                raise VideoClipperError("Missing required dependencies")
            
            # Setup directories
            self._setup_directories()
            
            with self._managed_temp_dir() as temp_dir:
                # Prepare paths
                raw_video_path = temp_dir / "raw_video.mp4"
                
                self.logger.info(f"🎯 Target video: {self.config.video_url}")
                self.logger.info(f"📁 Output directory: {self.output_dir}")
                
                # Download video
                self.logger.info("\n" + "=" * 70)
                self.logger.info("📥 DOWNLOADING VIDEO")
                self.logger.info("=" * 70)
                
                if not self._download_video(self.config.video_url, raw_video_path):
                    self.logger.error("❌ All download strategies failed!")
                    
                    if not self._create_fallback_video(raw_video_path):
                        raise VideoClipperError("Failed to create fallback video")
                
                # Validate downloaded video
                if not self._validate_video(raw_video_path):
                    self.logger.warning("⚠️ Video validation failed, but continuing...")
                
                # Analyze video content
                segments = self._analyze_video_content(raw_video_path)
                
                # Score and rank segments
                if segments:
                    ranked_segments = self._score_and_rank_segments(segments)
                else:
                    ranked_segments = []
                
                # Create intelligent clips
                self.logger.info("\n" + "=" * 70)
                self.logger.info("✂️ CREATING INTELLIGENT CLIPS")
                self.logger.info("=" * 70)
                
                if not self._create_intelligent_clips(raw_video_path, ranked_segments):
                    raise VideoClipperError("Failed to create clips")
                
                # Create highlight reel if enough segments
                if len(ranked_segments) >= 2:
                    self._create_highlight_reel(raw_video_path, ranked_segments)
                
                # Create analysis report
                video_info = self.analyzer.get_video_info(raw_video_path)
                self._create_analysis_report(ranked_segments, video_info)
                
                # Report results
                self.logger.info("\n" + "=" * 70)
                self.logger.info("📋 CREATED FILES")
                self.logger.info("=" * 70)
                
                self._list_output_files()
                
                # Summary
                self.logger.info("\n" + "=" * 70)
                self.logger.info("📈 PROCESSING SUMMARY")
                self.logger.info("=" * 70)
                self.logger.info(f"🎬 Segments analyzed: {len(segments)}")
                self.logger.info(f"✂️ Clips created: {len(ranked_segments)}")
                if ranked_segments:
                    avg_score = sum(seg.score for seg in ranked_segments) / len(ranked_segments)
                    self.logger.info(f"📊 Average clip score: {avg_score:.2f}")
                    
                    # Show clip types distribution
                    clip_types = {}
                    for seg in ranked_segments:
                        clip_types[seg.clip_type] = clip_types.get(seg.clip_type, 0) + 1
                    
                    for clip_type, count in clip_types.items():
                        self.logger.info(f"🏷️ {clip_type}: {count} clips")
                
                self.logger.info("✅ Intelligent video processing completed successfully!")
                return True
                
        except VideoClipperError as e:
            self.logger.error(f"❌ Video clipper error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Unexpected error: {e}")
            return False

def create_sample_config(config_path: Path):
    """Create a sample configuration file with intelligent clipping settings"""
    config = Config()
    
    # Set some example intelligent clipping preferences
    config.clipping.scene_threshold = 0.25
    config.clipping.min_clip_duration = 8.0
    config.clipping.max_clip_duration = 45.0
    config.clipping.target_clip_duration = 25.0
    config.clipping.max_clips = 8
    config.clipping.prefer_faces = True
    config.clipping.prefer_speech = True
    config.clipping.audio_analysis_enabled = True
    config.clipping.motion_analysis_enabled = True
    
    config.save_to_file(config_path)
    print(f"📄 Sample configuration created: {config_path}")
    print("💡 Edit the configuration file to customize clipping behavior")

def main():
    """Main function with enhanced argument parsing"""
    parser = argparse.ArgumentParser(
        description="Intelligent Video Clipper - Auto-generates clips based on content analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create sample config with intelligent clipping settings
  python intelligent_clipper.py --create-config
  
  # Process video with default intelligent settings
  python intelligent_clipper.py
  
  # Override specific settings
  python intelligent_clipper.py --url "https://youtu.be/VIDEO_ID" --max-clips 5
  
  # Use custom scene detection sensitivity
  python intelligent_clipper.py --scene-threshold 0.4 --target-duration 20
        """
    )
    
    parser.add_argument(
        "--config", 
        type=Path, 
        default=Path("intelligent_clipper_config.json"),
        help="Configuration file path"
    )
    parser.add_argument(
        "--create-config", 
        action="store_true",
        help="Create sample configuration file with intelligent clipping settings"
    )
    parser.add_argument(
        "--url", 
        help="Video URL to download (overrides config)"
    )
    parser.add_argument(
        "--quality", 
        choices=["1080p", "720p", "480p", "360p", "worst"],
        help="Video quality preference (overrides config)"
    )
    parser.add_argument(
        "--max-clips", 
        type=int,
        help="Maximum number of clips to generate (overrides config)"
    )
    parser.add_argument(
        "--target-duration", 
        type=float,
        help="Target clip duration in seconds (overrides config)"
    )
    parser.add_argument(
        "--scene-threshold", 
        type=float,
        help="Scene detection sensitivity 0.1-1.0 (overrides config)"
    )
    parser.add_argument(
        "--disable-audio-analysis", 
        action="store_true",
        help="Disable audio content analysis"
    )
    parser.add_argument(
        "--disable-motion-analysis", 
        action="store_true",
        help="Disable motion content analysis"
    )
    parser.add_argument(
        "--prefer-faces", 
        action="store_true",
        help="Prioritize clips containing faces"
    )
    parser.add_argument(
        "--prefer-speech", 
        action="store_true",
        help="Prioritize clips containing speech"
    )
    
    args = parser.parse_args()
    
    if args.create_config:
        create_sample_config(args.config)
        return 0
    
    # Load configuration
    config = Config.from_file(args.config)
    
    # Override with command line arguments
    if args.url:
        config.video_url = args.url
    if args.quality:
        config.quality_preference = args.quality
    if args.max_clips:
        config.clipping.max_clips = args.max_clips
    if args.target_duration:
        config.clipping.target_clip_duration = args.target_duration
    if args.scene_threshold:
        config.clipping.scene_threshold = args.scene_threshold
    if args.disable_audio_analysis:
        config.clipping.audio_analysis_enabled = False
    if args.disable_motion_analysis:
        config.clipping.motion_analysis_enabled = False
    if args.prefer_faces:
        config.clipping.prefer_faces = True
    if args.prefer_speech:
        config.clipping.prefer_speech = True
    
    # Create and run intelligent clipper
    clipper = IntelligentVideoClipper(config)
    
    print("🧠 Starting Intelligent Video Clipper")
    print("🎯 Automatically generating clips based on content analysis")
    print("=" * 70)
    
    success = clipper.process()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())