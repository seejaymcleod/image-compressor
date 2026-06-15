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

def apply_dirty_pixels(img, out_format):
    if out_format.upper() in ["JPEG", "JPG"]:
        return img  # JPEGs do not support transparency/alpha channel
        
    if img.mode not in ('RGBA', 'LA'):
        img = img.convert('RGBA')
        
    w, h = img.size
    pixels = img.load()
    
    if img.mode == 'RGBA':
        r, g, b, a = pixels[0, 0]
        pixels[0, 0] = (r, g, b, 1)
        r, g, b, a = pixels[w - 1, h - 1]
        pixels[w - 1, h - 1] = (r, g, b, 1)
    elif img.mode == 'LA':
        l, a = pixels[0, 0]
        pixels[0, 0] = (l, 1)
        l, a = pixels[w - 1, h - 1]
        pixels[w - 1, h - 1] = (l, 1)
        
    return img

class ProgressConsole:
    def __init__(self, total_files):
        self.total_files = total_files
        self.current_file_idx = 0
        self.file_name = ""
        self.out_format = ""
        self.orig_size_mb = 0
        
        self.file_progress_total = 1
        self.file_progress_current = 0
        self.file_status = ""
        self.lines_printed = 0
        
    def start_file(self, file_name, out_format, orig_size_mb):
        self.current_file_idx += 1
        self.file_name = file_name
        self.out_format = out_format
        self.orig_size_mb = orig_size_mb
        self.file_progress_total = 100
        self.file_progress_current = 0
        self.file_status = f"Making file with format {out_format.upper()}..."
        self.update()
        
    def update_file(self, current, total, status):
        self.file_progress_current = current
        self.file_progress_total = total
        self.file_status = status
        self.update()

    def print_warning(self, msg):
        self.clear()
        print(f"  [!] {msg}")
        self.update()
        
    def skip_file(self, file_name, message):
        self.clear()
        print(f"[-] Skipped {file_name}: {message}")
        self.lines_printed = 0
        
    def finish_file(self, message):
        self.file_progress_current = self.file_progress_total
        self.file_status = "Done!"
        self.update()
        
        self.clear()
        dir_pct = int((self.current_file_idx / self.total_files) * 100)
        print(f"[{dir_pct:3}%] {self.file_name} -> {self.out_format.upper()} | Confirmed: {message}")
        self.lines_printed = 0

    def clear(self):
        if self.lines_printed > 0:
            sys.stdout.write(f"\033[{self.lines_printed}A")
            for _ in range(self.lines_printed):
                sys.stdout.write("\033[K\n")
            sys.stdout.write(f"\033[{self.lines_printed}A")
            self.lines_printed = 0

    def get_bar(self, current, total, width=30):
        if total <= 0:
            return "[" + " " * width + "]   0%"
        pct = min(1.0, current / total)
        filled = int(width * pct)
        bar = "█" * filled + "-" * (width - filled)
        return f"[{bar}] {int(pct * 100):3}%"

    def update(self):
        self.clear()
        
        dir_bar = self.get_bar(self.current_file_idx - 1, self.total_files) 
        print(f"Directory: {dir_bar} ({self.current_file_idx}/{self.total_files})")
        
        print(f"File:      {self.file_name} ({self.orig_size_mb:.2f} MB)")
        
        file_bar = self.get_bar(self.file_progress_current, self.file_progress_total)
        print(f"Progress:  {file_bar} | {self.file_status}")
        
        self.lines_printed = 3
        sys.stdout.flush()

def compress_image(input_path, output_path, max_file_size, orig_size, out_format="WEBP", scale=1.0, max_dim=8192, forcesquare=None, dirty=False, console=None):
    if console is None:
        console = type("DummyConsole", (), {"update_file": lambda *a: None, "finish_file": print, "print_warning": print})()

    try:
        Image.MAX_IMAGE_PIXELS = None
        img = Image.open(input_path)
        img = ImageOps.exif_transpose(img)
        
        if out_format.upper() in ["JPEG", "JPG"] and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
    except Exception as e:
        console.print_warning(f"Failed to open {input_path.name}: {e}")
        return

    console.update_file(5, 100, "Calculating dimensions...")
    fit_scale = 1.0
    img_max_edge = max(img.width, img.height)
    if img_max_edge > max_dim:
        fit_scale = max_dim / img_max_edge
        
    base_scale = fit_scale * scale
    current_scale = base_scale
    new_size = (round(img.width * current_scale), round(img.height * current_scale))
    new_size = (max(1, new_size[0]), max(1, new_size[1]))
    
    console.update_file(10, 100, "Initial resizing...")
    resized_img = img.resize(new_size, Image.Resampling.LANCZOS) if current_scale < 1.0 else img.copy()
    
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
            
    if forcesquare is not None and dirty:
        resized_img = apply_dirty_pixels(resized_img, out_format)
        
    console.update_file(20, 100, "Saving test image...")
    if out_format.upper() == "PNG":
        resized_img.save(output_path, "PNG")
    else:
        resized_img.save(output_path, out_format, quality=85)
        
    file_size = os.path.getsize(output_path)
    
    best_sf = None
    if file_size <= max_file_size:
        best_sf = 1.0
        console.update_file(50, 100, "Fits at max scale!")
    else:
        low_sf = 0.1
        high_sf = 1.0
        
        for i in range(5):
            sf = (low_sf + high_sf) / 2
            console.update_file(20 + i * 6, 100, f"Binary search scale {i+1}/5...")
            current_scale = base_scale * sf
            new_size = (round(img.width * current_scale), round(img.height * current_scale))
            new_size = (max(1, new_size[0]), max(1, new_size[1]))
            
            resized_img = img.resize(new_size, Image.Resampling.LANCZOS) if current_scale < 1.0 else img.copy()
            
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
                    
            if forcesquare is not None and dirty:
                resized_img = apply_dirty_pixels(resized_img, out_format)
                
            if out_format.upper() == "PNG":
                resized_img.save(output_path, "PNG")
            else:
                resized_img.save(output_path, out_format, quality=85)
                
            file_size = os.path.getsize(output_path)
            
            if file_size <= max_file_size:
                best_sf = sf
                low_sf = sf
            else:
                high_sf = sf
                
        if best_sf is None:
            best_sf = 0.1
            console.print_warning("Image is still too large at minimum scale (0.1).")

    console.update_file(60, 100, "Applying optimal scale...")
    current_scale = base_scale * best_sf
    new_size = (round(img.width * current_scale), round(img.height * current_scale))
    new_size = (max(1, new_size[0]), max(1, new_size[1]))
    resized_img = img.resize(new_size, Image.Resampling.LANCZOS) if current_scale < 1.0 else img.copy()
    
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
            
    if forcesquare is not None and dirty:
        resized_img = apply_dirty_pixels(resized_img, out_format)

    if out_format.upper() == "PNG":
        console.update_file(80, 100, "Optimizing PNG output...")
        resized_img.save(output_path, "PNG", optimize=True)
        file_size = os.path.getsize(output_path)
        console.finish_file(f"Size: {file_size / (1024 * 1024):.2f} MB")
    else:
        low_q = 1
        high_q = 100
        best_q = None
        
        q_iters = 0
        while low_q <= high_q:
            q_iters += 1
            quality = (low_q + high_q) // 2
            console.update_file(60 + q_iters * 4, 100, f"Quality search (q={quality})...")
            resized_img.save(output_path, out_format, quality=quality)
            file_size = os.path.getsize(output_path)
            
            if file_size <= max_file_size:
                best_q = quality
                if file_size >= max_file_size * 0.9:
                    break
                low_q = quality + 1
            else:
                high_q = quality - 1
                
        if best_q is not None:
            console.update_file(95, 100, "Saving optimal quality...")
            resized_img.save(output_path, out_format, quality=best_q)
            file_size = os.path.getsize(output_path)
            if file_size >= orig_size:
                console.print_warning(f"Notice: Compressed format is actually larger ({file_size / (1024 * 1024):.2f} MB).")
            console.finish_file(f"Size: {file_size / (1024 * 1024):.2f} MB")
        else:
            console.update_file(95, 100, "Saving minimum quality...")
            resized_img.save(output_path, out_format, quality=1)
            file_size = os.path.getsize(output_path)
            console.finish_file(f"Saved at min quality 1. Size: {file_size / (1024 * 1024):.2f} MB")

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
    parser.add_argument("--dirty", action="store_true", help="Add a nearly transparent pixel (opacity 1/255) to the top-left and bottom-right corners of the padded canvas to prevent auto-trimming.")
    parser.add_argument("--preset", type=str, choices=["kanka", "viewer"], help="Apply preset configuration")
    args = parser.parse_args()
    
    if args.preset == "kanka":
        if "--size" not in sys.argv:
            args.size = "9.5"
        if "--format" not in sys.argv:
            args.format = "webp"
        if "--max-dim" not in sys.argv:
            args.max_dim = 8192
        if args.path is None and args.dir is None:
            args.path = "../"
            
    if args.preset == "viewer":
        if "--size" not in sys.argv:
            args.size = "50"
        if "--format" not in sys.argv:
            args.format = "webp"
        if "--max-dim" not in sys.argv:
            args.max_dim = 16000
        if args.path is None and args.dir is None:
            args.path = "../"
            
    max_file_size = parse_size(args.size) * 1024 * 1024
    out_format = "JPEG" if args.format.lower() == "jpg" else args.format.upper()
    ext = f".{args.format.lower()}"
    
    supported_exts = {".png", ".jpg", ".jpeg", ".webp"}
    
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
        
    output_dir.mkdir(exist_ok=True)
    image_files = [f for f in image_files if f.parent != output_dir]
    
    if not image_files:
        print(f"No supported image files ({', '.join(supported_exts)}) found.")
        return
        
    print(f"Found {len(image_files)} image files to process.\n")
    console = ProgressConsole(len(image_files))
    
    for img_file in image_files:
        orig_size_mb = os.path.getsize(img_file) / (1024 * 1024)
        
        output_path = output_dir / f"{img_file.stem}{ext}"
        
        if output_path.exists() and not args.overwrite:
            console.current_file_idx += 1
            console.skip_file(img_file.name, "already exists (use --overwrite to replace)")
            continue
            
        if output_path.resolve() == img_file.resolve():
            console.current_file_idx += 1
            console.skip_file(img_file.name, "would overwrite input file directly")
            continue
            
        console.start_file(img_file.name, out_format, orig_size_mb)
        compress_image(img_file, output_path, max_file_size, orig_size_mb * 1024 * 1024, out_format, scale=args.scale, max_dim=args.max_dim, forcesquare=args.forcesquare, dirty=args.dirty, console=console)
        
    print("\nAll done! Compressed files are in the 'compressed_for_kanka' folder.")

if __name__ == "__main__":
    main()
