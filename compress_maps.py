import argparse
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    print("Pillow library is required. Please install it using: pip install Pillow")
    sys.exit(1)

def parse_size(size_str):
    size_str = str(size_str).strip().upper()
    if size_str.endswith('MB'):
        return float(size_str[:-2])
    elif size_str.endswith('M'):
        return float(size_str[:-1])
    return float(size_str)

def compress_image(input_path, output_path, max_file_size, orig_size, out_format="WEBP", scale=1.0, max_dim=8192):
    # Open the image
    try:
        Image.MAX_IMAGE_PIXELS = None  # Disable decompression bomb protection for huge maps
        img = Image.open(input_path)
        img = ImageOps.exif_transpose(img) # Fixes EXIF orientation by permanently rotating the pixels
        
        # Ensure we are in RGB mode if saving to JPEG
        if out_format.upper() in ["JPEG", "JPG"] and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
    except Exception as e:
        print(f"Failed to open {input_path.name}: {e}")
        return

    scale_factor = scale
    
    if img.width * scale_factor > max_dim or img.height * scale_factor > max_dim:
        scale_factor = max_dim / max(img.width, img.height)
    
    while scale_factor >= 0.1:
        new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
        resized_img = img.resize(new_size, Image.Resampling.LANCZOS) if scale_factor < 1.0 else img
        
        print(f"Trying to compress {input_path.name} at {new_size[0]}x{new_size[1]}...")
        
        low = 1
        high = 100
        best_q_for_scale = None
        
        # Binary search for the optimal quality between 1 and 100
        while low <= high:
            quality = (low + high) // 2
            resized_img.save(output_path, out_format, quality=quality)
            file_size = os.path.getsize(output_path)
            
            if file_size <= max_file_size:
                best_q_for_scale = quality
                
                # If we are within 10% of the target size, it's perfect!
                if file_size >= max_file_size * 0.9:
                    break
                
                # Too small, try higher quality
                low = quality + 1
            else:
                # Too big, try lower quality
                high = quality - 1
                
        if best_q_for_scale is not None:
            # Re-save with best quality to ensure output_path has the right file
            resized_img.save(output_path, out_format, quality=best_q_for_scale)
            file_size = os.path.getsize(output_path)
            
            print(f"Optimal compression found: quality {best_q_for_scale}.")
            if file_size >= orig_size:
                print(f"Notice: The compressed {out_format} is actually larger than or equal to the original PNG ({file_size / (1024 * 1024):.2f} MB vs {orig_size / (1024 * 1024):.2f} MB). You might just want to use the original!")
            else:
                print(f"Success! {output_path.name} is now {file_size / (1024 * 1024):.2f} MB.")
            return
            
        print(f"Even at minimum quality, image is too large. Scaling dimensions down by 20%...")
        scale_factor *= 0.8
        
    print(f"Warning: {input_path.name} could not be compressed under {max_file_size / (1024 * 1024):.1f}MB without severe degradation.")

def main():
    parser = argparse.ArgumentParser(description="Compress PNG maps to WebP/JPEG format.")
    parser.add_argument("path", type=str, nargs="?", default=None, help="Path to a PNG file or directory containing PNG files (default: current directory)")
    parser.add_argument("--dir", type=str, default=None, help="Directory to scan (deprecated, use positional path instead)")
    parser.add_argument("--size", type=str, default="9.5", help="Target maximum file size in MB, e.g. '9.5' or '9.5MB' (default: 9.5)")
    parser.add_argument("--format", type=str, default="webp", choices=["webp", "jpeg", "jpg"], help="Output format (default: webp)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing compressed files instead of skipping them")
    parser.add_argument("--scale", type=float, default=1.0, help="Initial scale factor to resize image, preserving aspect ratio (default: 1.0)")
    parser.add_argument("--max-dim", type=int, default=8192, help="Maximum dimension (width or height) in pixels, preserving aspect ratio (default: 8192)")
    args = parser.parse_args()
    
    max_file_size = parse_size(args.size) * 1024 * 1024
    out_format = "JPEG" if args.format.lower() == "jpg" else args.format.upper()
    ext = f".{args.format.lower()}"
    
    # Resolve target path from positional argument, falling back to --dir or current directory
    input_path = args.path or args.dir or "."
    target_path = Path(input_path).resolve()
    
    if target_path.is_file():
        if target_path.suffix.lower() != ".png":
            print(f"Error: Target file '{target_path.name}' is not a PNG image.")
            return
        png_files = [target_path]
        output_dir = target_path.parent / "compressed_for_kanka"
    elif target_path.is_dir():
        png_files = list(target_path.glob("*.png"))
        output_dir = target_path / "compressed_for_kanka"
    else:
        print(f"Error: Path '{input_path}' does not exist.")
        return
        
    # Create the output directory
    output_dir.mkdir(exist_ok=True)
    
    if not png_files:
        print("No PNG files found in the directory.")
        return
        
    print(f"Found {len(png_files)} PNG files to process.")
    
    for png_file in png_files:
        orig_size = os.path.getsize(png_file)
        print(f"\nProcessing {png_file.name} (Original size: {orig_size / (1024 * 1024):.2f} MB)")
        
        output_path = output_dir / f"{png_file.stem}{ext}"
        
        if output_path.exists() and not args.overwrite:
            print(f"Skipping {png_file.name}, compressed file already exists. Use --overwrite to replace it.")
            continue
            
        compress_image(png_file, output_path, max_file_size, orig_size, out_format, scale=args.scale, max_dim=args.max_dim)
        
    print("\nAll done! Compressed files are in the 'compressed_for_kanka' folder.")

if __name__ == "__main__":
    main()
