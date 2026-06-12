# Image Compressor for Kanka Maps

A Python script designed to optimize and compress large map images (PNG, WebP, JPEG, JPG) into WebP, JPEG, or PNG format, ensuring they fit within a target file size (e.g., Kanka's 9.5 MB limit) while retaining as much resolution and quality as possible.

The script uses a smart compression algorithm that automatically adjusts quality (for lossy WebP/JPEG) or scales down dimensions (while preserving aspect ratio) to meet your exact file size target.

## Features

- **File and Directory support**: Target a single image file or an entire directory of images.
- **Multi-Format Input & Output**: Convert between PNG, WebP, JPEG, and JPG seamlessly.
- **Smart Quality Compression**: For lossy formats (WebP/JPEG), performs a binary search to find the highest image quality parameter that fits within the target size constraint.
- **Lossless PNG Support**: Automatically resizes dimensions to fit within size limits without losing lossless image detail via quality quantization.
- **Aspect Ratio Preserved Sizing**: 
  - `--max-dim`: Set custom maximum dimension limits (default 8192px width/height).
  - `--scale`: Apply an initial manual resolution scaling factor (e.g., `0.5` for 50% width/height).
- **Auto-fallback Scaling**: If the image cannot fit the target size even at minimum quality/size, it will automatically scale down the resolution in 20% steps until it fits.

## Requirements

- Python 3
- [Pillow](https://pillow.readthedocs.io/en/stable/) library for image processing.

### Installation

Install Pillow using pip:

```bash
pip install Pillow
```

## Usage

Run the script by passing the target path (a single file or a directory containing images):

```bash
python3 compress_maps.py [path] [options]
```

### Positional Arguments
- `path` (Optional): Path to an image file or a directory containing image files. Defaults to the current directory (`.`).

### Optional Arguments
- `-h, --help`: Show the help message and exit.
- `--size SIZE`: Target maximum file size in MB. e.g., `9.5` or `9.5MB` (default: `9.5`).
- `--format {webp,jpeg,jpg,png}`: Output format (default: `webp`).
- `--scale SCALE`: Initial scale factor to resize image, preserving aspect ratio. e.g., `0.5` for 50% size (default: `1.0`).
- `--max-dim MAX_DIM`: Maximum dimension (width or height) in pixels, preserving aspect ratio (default: `8192`).
- `--overwrite`: Overwrite existing compressed files in the output folder instead of skipping them.

---

## Examples

### 1. Compress a single map to fit under 9.5 MB (default WebP)
```bash
python3 compress_maps.py Materia-Terrain.png
```

### 2. Convert a WebP map to a compressed PNG file
```bash
python3 compress_maps.py Materia-Terrain.webp --format png
```

### 3. Compress a map with a 50% scale reduction
```bash
python3 compress_maps.py Materia-Political.png --scale 0.5
```

### 4. Compress all maps in a folder to JPG with a 15 MB limit and a larger maximum dimension (12000px)
```bash
python3 compress_maps.py /path/to/maps --format jpg --size 15 --max-dim 12000
```

## Output

All compressed files will be saved in a new folder named `compressed_for_kanka` located inside the same directory as the target file(s).
