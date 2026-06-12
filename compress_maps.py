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

def compress_image(input_path, output_path, max_file_size, orig_size, out_format="WEBP", scale=1.0, max_dim=8192, forcesquare=None):
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

    # First, calculate scale needed to fit within max_dim
    fit_scale = 1.0
    img_max_edge = max(img.width, img.height)
    if img_max_edge > max_dim:
        fit_scale = max_dim / img_max_edge
        
    # Apply the user-defined scale on top of the fit scale
    base_scale = fit_scale * scale
    
    # Mathematical estimation to prevent useless compression attempts
    # Estimate the maximum number of pixels that can realistically fit in max_file_size
    # at lowest acceptable quality (roughly 0.15 bytes per pixel for lossy, 1.0 for PNG)
    # Note: we only count actual image pixels here because padding compresses to almost 0 bytes.
    bytes_per_pixel = 1.0 if out_format.upper() == "PNG" else 0.15
    max_estimated_pixels = max_file_size / bytes_per_pixel
    current_pixels = (img.width * base_scale) * (img.height * base_scale)
    
    if current_pixels > max_estimated_pixels:
        estimated_scale_reduction = (max_estimated_pixels / current_pixels) ** 0.5
        base_scale *= estimated_scale_reduction
        print(f"Mathematical estimation: Pre-scaling by an additional {estimated_scale_reduction*100:.1f}% to fit target size.")
    
    scale_factor = 1.0
    while scale_factor >= 0.1:
        current_scale = base_scale * scale_factor
        new_size = (int(img.width * current_scale), int(img.height * current_scale))
        
        # Prevent 0-size dimensions
        new_size = (max(1, new_size[0]), max(1, new_size[1]))
        
        resized_img = img.resize(new_size, Image.Resampling.LANCZOS) if current_scale < 1.0 else img
        
        # Apply forcesquare padding right before checking size/saving
        if forcesquare is not None:
            sq_edge = max(resized_img.width, resized_img.height) if forcesquare == -1 else forcesquare
            if resized_img.width != sq_edge or resized_img.height != sq_edge:
                if resized_img.mode == 'P':
                    resized_img = resized_img.convert("RGBA")
                bg_color = (0, 0, 0, 0) if resized_img.mode == 'RGBA' else (0, 0, 0)
                sq_img = Image.new(resized_img.mode, (sq_edge, sq_edge), bg_color)
                offset = ((sq_edge - resized_img.width) // 2, (sq_edge - resized_img.height) // 2)
                sq_img.paste(resized_img, offset)
                resized_img = sq_img
        
        print(f"Trying to compress {input_path.name} at {resized_img.width}x{resized_img.height} (image content: {new_size[0]}x{new_size[1]})...")
        
        if out_format.upper() == "PNG":
            # Save lossless PNG with optimization
            resized_img.save(output_path, "PNG", optimize=True)
            file_size = os.path.getsize(output_path)
            
            if file_size <= max_file_size:
                print(f"Success! {output_path.name} is now {file_size / (1024 * 1024):.2f} MB.")
                return
        else:
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
                    print(f"Notice: The compressed {out_format} is actually larger than or equal to the original ({file_size / (1024 * 1024):.2f} MB vs {orig_size / (1024 * 1024):.2f} MB). You might just want to use the original!")
                else:
                    print(f"Success! {output_path.name} is now {file_size / (1024 * 1024):.2f} MB.")
                return
            
        print(f"Even at minimum quality/size, image is too large. Scaling dimensions down by 20%...")
        scale_factor *= 0.8
        
    print(f"Warning: {input_path.name} could not be compressed under {max_file_size / (1024 * 1024):.1f}MB without severe degradation.")

def main():
    parser = argparse.ArgumentParser(description="Compress PNG maps to WebP/JPEG format.")
    parser.add_argument("path", type=str, nargs="?", default=None, help="Path to a PNG file or directory containing PNG files (default: current directory)")
    parser.add_argument("--dir", type=str, default=None, help="Directory to scan (deprecated, use positional path instead)")
    parser.add_argument("--size", type=str, default="9.5", help="Target maximum file size in MB, e.g. '9.5' or '9.5MB' (default: 9.5)")
    parser.add_argument("--format", type=str, default="webp", choices=["webp", "jpeg", "jpg", "png"], help="Output format (default: webp)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing compressed files instead of skipping them")
    parser.add_argument("--scale", type=float, default=1.0, help="Initial scale factor to resize image, preserving aspect ratio (default: 1.0)")
    parser.add_argument("--max-dim", type=int, default=8192, help="Maximum dimension (width or height) in pixels, preserving aspect ratio (default: 8192)")
    parser.add_argument("--forcesquare", nargs='?', const=-1, default=None, type=int, help="Expand canvas size to a square. Provide an optional dimension (e.g. --forcesquare 4096), otherwise defaults to the longer edge.")
    args = parser.parse_args()
    
    max_file_size = parse_size(args.size) * 1024 * 1024
    out_format = "JPEG" if args.format.lower() == "jpg" else args.format.upper()
    ext = f".{args.format.lower()}"
    
    # Supported input and output extensions
    supported_exts = {".png", ".jpg", ".jpeg", ".webp"}
    
    # Resolve target path from positional argument, falling back to --dir or current directory
    input_path = args.path or args.dir or "."
    target_path = Path(input_path).resolve()
    
    if target_path.is_file():
        if target_path.suffix.lower() not in supported_exts:
            print(f"Error: Target file '{target_path.name}' is not a supported image format ({', '.join(supported_exts)}).")
            return
        image_files = [target_path]
        output_dir = target_path.parent / "compressed_for_kanka"
    elif target_path.is_dir():
        image_files = []
        for ext_name in supported_exts:
            image_files.extend(target_path.glob(f"*{ext_name}"))
            image_files.extend(target_path.glob(f"*{ext_name.upper()}"))
        image_files = sorted(list(set(image_files)))
        output_dir = target_path / "compressed_for_kanka"
    else:
        print(f"Error: Path '{input_path}' does not exist.")
        return
        
    # Create the output directory
    output_dir.mkdir(exist_ok=True)
    
    # Filter out files that are already inside the output_dir
    image_files = [f for f in image_files if f.parent != output_dir]
    
    if not image_files:
        print(f"No supported image files ({', '.join(supported_exts)}) found.")
        return
        
    print(f"Found {len(image_files)} image files to process.")
    
    for img_file in image_files:
        orig_size = os.path.getsize(img_file)
        print(f"\nProcessing {img_file.name} (Original size: {orig_size / (1024 * 1024):.2f} MB)")
        
        output_path = output_dir / f"{img_file.stem}{ext}"
        
        if output_path.exists() and not args.overwrite:
            print(f"Skipping {img_file.name}, compressed file already exists. Use --overwrite to replace it.")
            continue
            
        if output_path.resolve() == img_file.resolve():
            print(f"Skipping {img_file.name} to avoid overwriting input file directly.")
            continue
            
        compress_image(img_file, output_path, max_file_size, orig_size, out_format, scale=args.scale, max_dim=args.max_dim, forcesquare=args.forcesquare)
        
    print("\nAll done! Compressed files are in the 'compressed_for_kanka' folder.")

if __name__ == "__main__":
    main()
