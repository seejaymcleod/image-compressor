# Image Compressor for Kanka Maps

A Python script designed to optimize and compress large map images (PNG) into WebP or JPEG format, ensuring they fit within a target file size (e.g., Kanka's 9.5 MB limit) while retaining as much resolution and quality as possible.

The script uses a smart binary search compression algorithm that automatically adjusts image quality and scales down dimensions (while preserving aspect ratio) to meet your exact file size target.

## Features

- **File and Directory support**: Target a single PNG map or an entire directory of maps.
- **Smart Quality Compression**: Performs a binary search to find the highest image quality parameter that fits within the target size constraint.
- **Aspect Ratio Preserved Sizing**: 
  - `--max-dim`: Set custom maximum dimension limits (default 8192px width/height).
  - `--scale`: Apply an initial manual resolution scaling factor (e.g., `0.5` for 50% width/height).
- **Auto-fallback Scaling**: If the image cannot fit the target size even at minimum quality, it will automatically scale down the resolution in 20% steps until it fits.

## Requirements

- Python 3
- [Pillow](https://pillow.readthedocs.io/en/stable/) library for image processing.

### Installation

Install Pillow using pip:

```bash
pip install Pillow
```

## Usage

Run the script by passing the target path (a single PNG file or a directory containing PNGs):

```bash
python3 compress_maps.py [path] [options]
```

### Positional Arguments
- `path` (Optional): Path to a PNG file or a directory containing PNG files. Defaults to the current directory (`.`).

### Optional Arguments
- `-h, --help`: Show the help message and exit.
- `--size SIZE`: Target maximum file size in MB. e.g., `9.5` or `9.5MB` (default: `9.5`).
- `--format {webp,jpeg,jpg}`: Output format (default: `webp`).
- `--scale SCALE`: Initial scale factor to resize image, preserving aspect ratio. e.g., `0.5` for 50% size (default: `1.0`).
- `--max-dim MAX_DIM`: Maximum dimension (width or height) in pixels, preserving aspect ratio (default: `8192`).
- `--overwrite`: Overwrite existing compressed files in the output folder instead of skipping them.

---

## Examples

### 1. Compress a single map to fit under 9.5 MB (default WebP)
```bash
python3 compress_maps.py Materia-Terrain.png
```

### 2. Compress all maps in a directory to WebP
```bash
python3 compress_maps.py /path/to/maps
```

### 3. Compress a map with a 50% scale reduction
```bash
python3 compress_maps.py Materia-Political.png --scale 0.5
```

### 4. Compress all maps to JPG with a 15 MB limit and a larger maximum dimension (12000px)
```bash
python3 compress_maps.py /path/to/maps --format jpg --size 15 --max-dim 12000
```

## Output

All compressed files will be saved in a new folder named `compressed_for_kanka` located inside the same directory as the target file(s).
