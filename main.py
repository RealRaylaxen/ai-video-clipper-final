#!/usr/bin/env python3
"""
AI Video Clipper - Main Processing Script
Run via GitHub Actions or locally with FFmpeg
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def parse_args():
    parser = argparse.ArgumentParser(description="AI Video Clipper - Extract clips from video")
    parser.add_argument("--url", required=True, help="Video URL or file path")
    parser.add_argument("--start", type=int, default=0, help="Start time in seconds")
    parser.add_argument("--end", type=int, default=30, help="End time in seconds")
    parser.add_argument("--output-dir", default="./clips", help="Output directory")
    parser.add_argument("--quality", default="1080p", choices=["480p", "720p", "1080p", "4k"], help="Output quality")
    parser.add_argument("--format", default="mp4", choices=["mp4", "webm", "mov", "gif"], help="Output format")
    parser.add_argument("--vertical", action="store_true", help="Crop to 9:16 vertical format")
    parser.add_argument("--subtitle", default="🔥 HIGH VIRAL MOMENT 🔥", help="Burned-in subtitle text")
    parser.add_argument("--no-upload", action="store_true", help="Skip cloud upload")
    return parser.parse_args()


def get_quality_settings(quality: str) -> tuple:
    """Get resolution and bitrate based on quality setting"""
    settings = {
        "480p": ("854:480", "2000k"),
        "720p": ("1280:720", "5000k"),
        "1080p": ("1920:1080", "10000k"),
        "4k": ("3840:2160", "35000k"),
    }
    return settings.get(quality, settings["1080p"])


def download_video(url: str, output_path: str) -> str:
    """Download video using yt-dlp or return path if local file"""
    if url.startswith(("http://", "https://")):
        # Check if it's a direct video file
        if any(url.endswith(ext) for ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]):
            print(f"[->] Direct video file detected: {url}")
            # For direct URLs, we'd need to download it
            result = subprocess.run(
                ["curl", "-L", "-o", output_path, url],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"[!] Error downloading: {result.stderr}")
                sys.exit(1)
            return output_path

        # Use yt-dlp for platforms like YouTube, TikTok, etc.
        print(f"[->] Downloading from: {url}")
        result = subprocess.run(
            ["yt-dlp", "-f", "best", "-o", output_path, url],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"[!] yt-dlp error: {result.stderr}")
            sys.exit(1)
        return output_path
    else:
        # Local file
        return url


def extract_clip(input_file: str, output_file: str, start: int, end: int, quality: str, format: str, vertical: bool = False, subtitle: str = ""):
    """Extract clip using FFmpeg with optional vertical crop and burned-in subtitle"""
    resolution, bitrate = get_quality_settings(quality)
    duration = end - start

    print(f"[->] Extracting clip: {start}s - {end}s ({duration}s)")
    print(f"[->] Quality: {quality} ({resolution})")
    if vertical:
        print(f"[->] Vertical crop: 9:16 enabled")
    if subtitle:
        print(f"[->] Subtitle: {subtitle}")

    # Build video filter chain
    video_filters = []

    # Vertical crop: crop to 9:16 (ih*9/16:ih)
    if vertical:
        video_filters.append("crop=ih*9/16:ih")

    # Add subtitle using drawtext on lower third
    if subtitle:
        # Escape special characters for FFmpeg
        escaped_text = subtitle.replace("'", "\\'").replace(":", "\\:")
        # Position in lower third (bottom 15% of frame, centered)
        video_filters.append(
            f"drawtext=text='{escaped_text}':fontcolor=white:fontsize=h/12:"
            f"x=(w-text_w)/2:y=h*0.85:borderw=2:bordercolor=black:shadowcolor=black:shadowx=2:shadowy=2"
        )

    # Apply scaling (always last to ensure correct output resolution)
    if vertical:
        video_filters.append("scale=1080:1920")
    else:
        video_filters.append(f"scale={resolution}")

    # Build FFmpeg command
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", input_file,
        "-t", str(duration),
        "-vf", ",".join(video_filters),
        "-b:v", bitrate,
        "-c:v", "libx264",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "192k",
    ]

    if format == "gif":
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", input_file,
            "-t", str(duration),
            "-vf", f"fps=15,scale={resolution.split(':')[0]}:-1:flags=lanczos",
            "-loop", "0",
            output_file
        ]
    else:
        cmd.extend(["-movflags", "+faststart", output_file])

    print(f"[...] Running: ffmpeg -ss {start}s -t {duration}s -vf \"{','.join(video_filters)}\"")
    print(f"[...] Output: {output_file}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[!] FFmpeg error: {result.stderr}")
        sys.exit(1)

    print(f"[OK] Clip saved: {output_file}")
    return output_file


def upload_to_free_cloud(file_path: str) -> str:
    """Upload completed clip to bashupload.com via curl, extract download URL"""
    if not Path(file_path).exists():
        print(f"[!] File not found: {file_path}")
        return ""

    print(f"[->] Uploading to bashupload.com...")

    # Upload using curl to bashupload.com
    cmd = [
        "curl", "-s", "-F", f"file=@{file_path}", "https://bashupload.com/"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[!] Upload error: {result.stderr}")
        return ""

    # Extract the raw download URL from response
    # Response format: "Your file is available at: https://bashupload.com/filename\n..."
    output = result.stdout
    print(f"[...] Server response: {output[:200]}...")

    # Try to extract URL using regex
    url_match = re.search(r'https://bashupload\.com/[a-zA-Z0-9_-]+', output)
    if url_match:
        download_url = url_match.group(0)
        print(f"[OK] Upload complete!")
        return download_url

    # Fallback: try alternative pattern
    alt_match = re.search(r'bashupload\.com/[a-zA-Z0-9_-]+', output)
    if alt_match:
        download_url = f"https://{alt_match.group(0)}"
        print(f"[OK] Upload complete!")
        return download_url

    # If no URL found, return the raw output for debugging
    print(f"[!] Could not extract URL from response")
    print(f"[...] Raw output: {output[:500]}")
    return output.strip()


def get_video_duration(input_file: str) -> int:
    """Get video duration in seconds"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        try:
            return int(float(result.stdout.strip()))
        except ValueError:
            pass
    return 0


def generate_thumbnail(input_file: str, output_file: str, timestamp: int = 5):
    """Generate thumbnail at specified timestamp"""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", input_file,
        "-vframes", "1",
        "-vf", "scale=320:-1",
        output_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[OK] Thumbnail: {output_file}")


def main():
    args = parse_args()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("AI VIDEO CLIPPER - Vertical + Subtitle Pipeline")
    print("=" * 60)
    print(f"Input URL:  {args.url}")
    print(f"Clip:       {args.start}s - {args.end}s")
    print(f"Quality:    {args.quality}")
    print(f"Format:     {args.format}")
    print(f"Vertical:   {args.vertical}")
    print(f"Subtitle:   {args.subtitle}")
    print(f"Cloud Upload: {'YES' if not args.no_upload else 'NO'}")
    print("=" * 60)

    # Determine output filename
    parsed = urlparse(args.url)
    filename = Path(parsed.path).stem or "video"
    suffix = "_vertical" if args.vertical else ""
    output_file = output_dir / f"{filename}_clip_{args.start}-{args.end}{suffix}.{args.format}"
    thumbnail_file = output_dir / f"{filename}_thumb.jpg"

    # Download video
    temp_file = output_dir / f"{filename}_temp.mp4"
    input_file = download_video(args.url, str(temp_file))

    # Get duration if not specified
    if args.end == 0:
        duration = get_video_duration(input_file)
        if duration > 0:
            args.end = min(duration, 30)
            print(f"[i] Video duration: {duration}s, using {args.end}s clip")

    # Extract clip with vertical crop and subtitle
    extract_clip(
        input_file,
        str(output_file),
        args.start,
        args.end,
        args.quality,
        args.format,
        vertical=args.vertical,
        subtitle=args.subtitle
    )

    # Generate thumbnail
    generate_thumbnail(input_file, str(thumbnail_file), args.start + 2)

    # Cleanup temp file if different from input
    if input_file != args.url and Path(input_file).exists():
        Path(input_file).unlink()

    # Upload to cloud if enabled
    download_url = ""
    if not args.no_upload:
        download_url = upload_to_free_cloud(str(output_file))

    print("=" * 60)
    print("PROCESSING COMPLETE!")
    print("=" * 60)
    print(f"Local Output: {output_file}")
    if download_url:
        print(f"Cloud URL:    {download_url}")
        print(f"\n📎 Share this URL: {download_url}")
    print("=" * 60)


if __name__ == "__main__":
    main()#!/usr/bin/env python3
"""
AI Video Clipper - Main Processing Script
Run via GitHub Actions or locally with FFmpeg
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def parse_args():
    parser = argparse.ArgumentParser(description="AI Video Clipper - Extract clips from video")
    parser.add_argument("--url", required=True, help="Video URL or file path")
    parser.add_argument("--start", type=int, default=0, help="Start time in seconds")
    parser.add_argument("--end", type=int, default=30, help="End time in seconds")
    parser.add_argument("--output-dir", default="./clips", help="Output directory")
    parser.add_argument("--quality", default="1080p", choices=["480p", "720p", "1080p", "4k"], help="Output quality")
    parser.add_argument("--format", default="mp4", choices=["mp4", "webm", "mov", "gif"], help="Output format")
    return parser.parse_args()


def get_quality_settings(quality: str) -> tuple:
    """Get resolution and bitrate based on quality setting"""
    settings = {
        "480p": ("854:480", "2000k"),
        "720p": ("1280:720", "5000k"),
        "1080p": ("1920:1080", "10000k"),
        "4k": ("3840:2160", "35000k"),
    }
    return settings.get(quality, settings["1080p"])


def download_video(url: str, output_path: str) -> str:
    """Download video using yt-dlp or return path if local file"""
    if url.startswith(("http://", "https://")):
        # Check if it's a direct video file
        if any(url.endswith(ext) for ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]):
            print(f"[->] Direct video file detected: {url}")
            # For direct URLs, we'd need to download it
            result = subprocess.run(
                ["curl", "-L", "-o", output_path, url],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"[!] Error downloading: {result.stderr}")
                sys.exit(1)
            return output_path

        # Use yt-dlp for platforms like YouTube, TikTok, etc.
        print(f"[->] Downloading from: {url}")
        result = subprocess.run(
            ["yt-dlp", "-f", "best", "-o", output_path, url],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"[!] yt-dlp error: {result.stderr}")
            sys.exit(1)
        return output_path
    else:
        # Local file
        return url


def extract_clip(input_file: str, output_file: str, start: int, end: int, quality: str, format: str):
    """Extract clip using FFmpeg"""
    resolution, bitrate = get_quality_settings(quality)
    duration = end - start

    print(f"[->] Extracting clip: {start}s - {end}s ({duration}s)")
    print(f"[->] Quality: {quality} ({resolution})")

    # Build FFmpeg command
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", input_file,
        "-t", str(duration),
        "-vf", f"scale={resolution}",
        "-b:v", bitrate,
        "-c:v", "libx264",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "192k",
    ]

    if format == "gif":
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", input_file,
            "-t", str(duration),
            "-vf", f"fps=15,scale={resolution.split(':')[0]}:-1:flags=lanczos",
            "-loop", "0",
            output_file
        ]
    else:
        cmd.extend(["-movflags", "+faststart", output_file])

    print(f"[...] Running: {' '.join(cmd[:6])}... {output_file}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[!] FFmpeg error: {result.stderr}")
        sys.exit(1)

    print(f"[OK] Clip saved: {output_file}")


def get_video_duration(input_file: str) -> int:
    """Get video duration in seconds"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        try:
            return int(float(result.stdout.strip()))
        except ValueError:
            pass
    return 0


def generate_thumbnail(input_file: str, output_file: str, timestamp: int = 5):
    """Generate thumbnail at specified timestamp"""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", input_file,
        "-vframes", "1",
        "-vf", "scale=320:-1",
        output_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[OK] Thumbnail: {output_file}")


def main():
    args = parse_args()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print("AI VIDEO CLIPPER")
    print("=" * 50)
    print(f"Input: {args.url}")
    print(f"Clip: {args.start}s - {args.end}s")
    print(f"Quality: {args.quality}")
    print(f"Format: {args.format}")
    print("=" * 50)

    # Determine output filename
    parsed = urlparse(args.url)
    filename = Path(parsed.path).stem or "video"
    output_file = output_dir / f"{filename}_clip_{args.start}-{args.end}.{args.format}"
    thumbnail_file = output_dir / f"{filename}_thumb.jpg"

    # Download video
    temp_file = output_dir / f"{filename}_temp.mp4"
    input_file = download_video(args.url, str(temp_file))

    # Get duration if not specified
    if args.end == 0:
        duration = get_video_duration(input_file)
        if duration > 0:
            args.end = min(duration, 30)
            print(f"[i] Video duration: {duration}s, using {args.end}s clip")

    # Extract clip
    extract_clip(input_file, str(output_file), args.start, args.end, args.quality, args.format)

    # Generate thumbnail
    generate_thumbnail(input_file, str(thumbnail_file), args.start + 2)

    # Cleanup temp file if different from input
    if input_file != args.url and Path(input_file).exists():
        Path(input_file).unlink()

    print("=" * 50)
    print("COMPLETE!")
    print(f"Output: {output_file}")
    print("=" * 50)


if __name__ == "__main__":
    main()
