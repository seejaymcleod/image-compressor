import argparse
import os
import sys
import io
import time
import concurrent.futures
import multiprocessing
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

class MultiProcessConsole:
    def __init__(self, total_files, num_workers, lock, shared_dict, completed_count):
        self.total_files = total_files
        self.num_workers = num_workers
        self.lock = lock
        self.shared_dict = shared_dict
        self.completed_count = completed_count
        
        self.lines_reserved = num_workers + 1
        
        for i in range(num_workers):
            self.shared_dict[i] = {"file": "", "progress": 0, "status": "Idle"}
            
        with self.lock:
            for _ in range(self.lines_reserved - 1):
                sys.stdout.write("\n")
            self.render()
            
    def get_bar(self, current, total, width=20):
        if total <= 0:
            return "[" + " " * width + "]   0%"
        pct = min(1.0, current / total)
        filled = int(width * pct)
        bar = "█" * filled + "-" * (width - filled)
        return f"[{bar}] {int(pct * 100):3}%"
        
    def render(self):
        sys.stdout.write(f"\r\033[{self.lines_reserved - 1}A")
        
        completed = self.completed_count.value
        dir_bar = self.get_bar(completed, self.total_files, width=30)
        sys.stdout.write(f"\033[KDirectory: {dir_bar} ({completed}/{self.total_files})\n")
        
        for i in range(self.num_workers):
            state = self.shared_dict[i]
            if state["file"]:
                bar = self.get_bar(state["progress"], 100, width=20)
                line = f"\033[KWorker {i+1}: {bar} | {state['file']} ({state['status']})"
            else:
                bar = self.get_bar(0, 100, width=20)
                line = f"\033[KWorker {i+1}: {bar} | Idle"
                
            if i < self.num_workers - 1:
                sys.stdout.write(line + "\n")
            else:
                sys.stdout.write(line)
                
        sys.stdout.write("\r")
        sys.stdout.flush()

    def _clear_ui(self):
        sys.stdout.write(f"\r\033[{self.lines_reserved - 1}A")
        for i in range(self.lines_reserved):
            if i < self.lines_reserved - 1:
                sys.stdout.write("\033[K\n")
            else:
                sys.stdout.write("\033[K")
        sys.stdout.write(f"\r\033[{self.lines_reserved - 1}A")

    def insert_log(self, text):
        with self.lock:
            self._clear_ui()
            print(text)
            for _ in range(self.lines_reserved - 1):
                sys.stdout.write("\n")
            self.render()

    def print_warning(self, file_name, msg):
        self.insert_log(f"  [!] {file_name}: {msg}")
            
    def skip_file(self, file_name, message):
        with self.lock:
            self.completed_count.value += 1
        self.insert_log(f"[-] Skipped {file_name}: {message}")
            
    def update_worker(self, worker_id, progress, status):
        with self.lock:
            state = self.shared_dict[worker_id]
            state["progress"] = progress
            state["status"] = status
            self.shared_dict[worker_id] = state
            self.render()
            
    def start_worker(self, worker_id, file_name):
        with self.lock:
            state = self.shared_dict[worker_id]
            state["file"] = file_name
            state["progress"] = 0
            state["status"] = "Calculating..."
            self.shared_dict[worker_id] = state
            self.render()
            
    def finish_worker(self, worker_id, file_name, out_format, message, elapsed_time=None):
        time_str = f" | Time: {elapsed_time:.1f}s" if elapsed_time is not None else ""
        log_msg = f"[OK] {file_name} -> {out_format.upper()} | {message}{time_str}"
        with self.lock:
            self.completed_count.value += 1
            state = self.shared_dict[worker_id]
            state["file"] = ""
            state["progress"] = 0
            state["status"] = "Idle"
            self.shared_dict[worker_id] = state
        self.insert_log(log_msg)

def compress_image(input_path, output_path, max_file_size, orig_size, out_format="WEBP", scale=1.0, max_dim=8192, forcesquare=None, dirty=False, console=None, worker_id=0):
    if console is None:
        console = type("DummyConsole", (), {"finish_worker": lambda *a, **k: None, "print_warning": lambda *a: None, "skip_file": lambda *a: None, "update_worker": lambda *a: None, "start_worker": lambda *a: None})()

    start_time = time.time()
    file_name = input_path.name
    try:
        Image.MAX_IMAGE_PIXELS = None
        img = Image.open(input_path)
        img = ImageOps.exif_transpose(img)
        
        if out_format.upper() in ["JPEG", "JPG"] and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
    except Exception as e:
        console.print_warning(file_name, f"Failed to open {file_name}: {e}")
        return

    console.update_worker(worker_id, 5, "Initial resize...")
    fit_scale = 1.0
    img_max_edge = max(img.width, img.height)
    if img_max_edge > max_dim:
        fit_scale = max_dim / img_max_edge
        
    base_scale = fit_scale * scale
    current_scale = base_scale
    new_size = (round(img.width * current_scale), round(img.height * current_scale))
    new_size = (max(1, new_size[0]), max(1, new_size[1]))
    
    console.update_worker(worker_id, 10, "Padding and prep...")
    resized_img = img.resize(new_size, Image.Resampling.LANCZOS) if current_scale < 1.0 else img.copy()
    
    def apply_forcesquare_and_dirty(image):
        if forcesquare is not None:
            sq_edge = max(image.width, image.height) if forcesquare == -1 else forcesquare
            if image.width != sq_edge or image.height != sq_edge:
                if image.mode == 'P':
                    image = image.convert("RGBA")
                bg_color = (0, 0, 0, 0) if image.mode == 'RGBA' else (0, 0, 0)
                sq_img = Image.new(image.mode, (sq_edge, sq_edge), bg_color)
                offset = ((sq_edge - image.width) // 2, (sq_edge - image.height) // 2)
                sq_img.paste(image, offset)
                image = sq_img
                
        if forcesquare is not None and dirty:
            image = apply_dirty_pixels(image, out_format)
        return image

    resized_img = apply_forcesquare_and_dirty(resized_img)
    
    console.update_worker(worker_id, 15, "Testing scale limit...")
    buf = io.BytesIO()
    if out_format.upper() == "PNG":
        resized_img.save(buf, "PNG")
    else:
        resized_img.save(buf, out_format, quality=85)
    file_size = buf.tell()
    
    best_sf = None
    if file_size <= max_file_size:
        best_sf = 1.0
    else:
        low_sf = 0.1
        high_sf = 1.0
        
        for i in range(5):
            sf = (low_sf + high_sf) / 2
            console.update_worker(worker_id, 20 + i * 6, f"Binary search scale {i+1}/5...")
            current_scale = base_scale * sf
            new_size = (round(img.width * current_scale), round(img.height * current_scale))
            new_size = (max(1, new_size[0]), max(1, new_size[1]))
            
            temp_img = img.resize(new_size, Image.Resampling.LANCZOS) if current_scale < 1.0 else img.copy()
            temp_img = apply_forcesquare_and_dirty(temp_img)
                
            buf = io.BytesIO()
            if out_format.upper() == "PNG":
                temp_img.save(buf, "PNG")
            else:
                temp_img.save(buf, out_format, quality=85)
            file_size = buf.tell()
            
            if file_size <= max_file_size:
                best_sf = sf
                low_sf = sf
            else:
                high_sf = sf
                
        if best_sf is None:
            best_sf = 0.1
            console.print_warning(file_name, "Image is still too large at minimum scale (0.1).")

    console.update_worker(worker_id, 50, "Applying optimal scale...")
    current_scale = base_scale * best_sf
    new_size = (round(img.width * current_scale), round(img.height * current_scale))
    new_size = (max(1, new_size[0]), max(1, new_size[1]))
    resized_img = img.resize(new_size, Image.Resampling.LANCZOS) if current_scale < 1.0 else img.copy()
    resized_img = apply_forcesquare_and_dirty(resized_img)

    if out_format.upper() == "PNG":
        console.update_worker(worker_id, 80, "Optimizing PNG output...")
        resized_img.save(output_path, "PNG", optimize=True)
        final_size = os.path.getsize(output_path)
        console.finish_worker(worker_id, file_name, out_format, f"Size: {final_size / (1024 * 1024):.2f} MB", elapsed_time=time.time() - start_time)
    else:
        low_q = 1
        high_q = 100
        best_q = None
        
        q_iters = 0
        while low_q <= high_q:
            q_iters += 1
            quality = (low_q + high_q) // 2
            console.update_worker(worker_id, 60 + q_iters * 4, f"Quality search q={quality}...")
            buf = io.BytesIO()
            resized_img.save(buf, out_format, quality=quality)
            file_size = buf.tell()
            
            if file_size <= max_file_size:
                best_q = quality
                if file_size >= max_file_size * 0.9:
                    break
                low_q = quality + 1
            else:
                high_q = quality - 1
                
        if best_q is not None:
            console.update_worker(worker_id, 95, "Saving final file...")
            resized_img.save(output_path, out_format, quality=best_q)
            final_size = os.path.getsize(output_path)
            if final_size >= orig_size:
                console.print_warning(file_name, f"Notice: Compressed format is actually larger ({final_size / (1024 * 1024):.2f} MB).")
            console.finish_worker(worker_id, file_name, out_format, f"Size: {final_size / (1024 * 1024):.2f} MB", elapsed_time=time.time() - start_time)
        else:
            console.update_worker(worker_id, 95, "Saving min quality...")
            resized_img.save(output_path, out_format, quality=1)
            final_size = os.path.getsize(output_path)
            console.finish_worker(worker_id, file_name, out_format, f"Saved at min quality 1. Size: {final_size / (1024 * 1024):.2f} MB", elapsed_time=time.time() - start_time)

def process_file_worker(img_file, output_dir, max_file_size, out_format, ext, args, console, worker_queue):
    worker_id = worker_queue.get()
    try:
        orig_size_mb = os.path.getsize(img_file) / (1024 * 1024)
        output_path = output_dir / f"{img_file.stem}{ext}"
        
        if output_path.exists() and not args.overwrite:
            console.skip_file(img_file.name, "already exists (use --overwrite to replace)")
            return
            
        if output_path.resolve() == img_file.resolve():
            console.skip_file(img_file.name, "would overwrite input file directly")
            return
            
        console.start_worker(worker_id, img_file.name)
        compress_image(img_file, output_path, max_file_size, orig_size_mb * 1024 * 1024, out_format, scale=args.scale, max_dim=args.max_dim, forcesquare=args.forcesquare, dirty=args.dirty, console=console, worker_id=worker_id)
    except Exception as e:
        console.print_warning(img_file.name, f"Unexpected error processing file: {e}")
    finally:
        worker_queue.put(worker_id)

def main():
    # Support for macos multiprocessing
    multiprocessing.set_start_method('spawn', force=True)

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
    
    num_workers = os.cpu_count() or 4
    num_workers = min(num_workers, len(image_files))

    manager = multiprocessing.Manager()
    lock = manager.Lock()
    completed = manager.Value('i', 0)
    shared_dict = manager.dict()
    worker_queue = manager.Queue()
    
    for i in range(num_workers):
        worker_queue.put(i)
        
    console = MultiProcessConsole(len(image_files), num_workers, lock, shared_dict, completed)
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(
                process_file_worker, 
                img_file, output_dir, max_file_size, out_format, ext, args, console, worker_queue
            ) for img_file in image_files
        ]
        for future in concurrent.futures.as_completed(futures):
            future.result() 

    print("\n" * num_workers)
    print("All done! Compressed files are in the 'compressed_for_kanka' folder.")

if __name__ == "__main__":
    main()
