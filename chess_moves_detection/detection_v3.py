# chess_mobile_fast.py
import cv2, numpy as np, time, json, os, glob, shutil
from typing import Tuple, List, Optional

# Optional: pip install tflite-runtime requests
# try:
#     import tflite_runtime.interpreter as tflite
# except Exception:
#     tflite = None
# try:
#     import requests
# except Exception:
#     requests = None

# ---- Config ----
WARP_SIZE = 512          # small and fast
INSET_FRAC = 0.08        # crop inside each cell to avoid grid lines
EXPAND_FRAC = 0.2       # expand square crop to include surrounding space (for pieces extending beyond boundaries)
GRID_SIZE = 10           # total grid including border (10x10 = 8x8 playing area + 1 square border on each side)
PLAYING_SIZE = 8         # actual playing area (8x8)
MAX_RESIZE = 640         # downscale longest side before detection
CANNY = (60, 180)
TILE_PX = 96             # model input size, set to your model
CLASS_NAMES = [
    "empty", "wp","wn","wb","wr","wq","wk","bp","bn","bb","br","bq","bk"
]
# Map index->symbol for FEN
IDX_TO_FEN = {
    0:"", 1:"P",2:"N",3:"B",4:"R",5:"Q",6:"K", 7:"p",8:"n",9:"b",10:"r",11:"q",12:"k"
}

# ---- Geometry ----
def _order_quad(pts: np.ndarray) -> np.ndarray:
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).reshape(4)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return np.array([tl, tr, br, bl], dtype=np.float32)

def _four_point_warp(bgr: np.ndarray, quad: np.ndarray, size: int = WARP_SIZE) -> Tuple[np.ndarray, np.ndarray]:
    src = _order_quad(quad)
    dst = np.array([[0,0],[size-1,0],[size-1,size-1],[0,size-1]], dtype=np.float32)
    H = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(bgr, H, (size, size), flags=cv2.INTER_LINEAR)
    return warped, H

# ---- Detection: largest 4-point contour ----
def find_board_quad_fast(bgr: np.ndarray, max_side: int = MAX_RESIZE, debug: bool = False) -> Tuple[Optional[np.ndarray], float, Optional[dict]]:
    """
    Find chess board quad in image by thresholding white background.
    Since the board is the only non-white object, we threshold to separate it from background.
    Returns: (quad, scale, debug_info)
    debug_info contains: thresholded, contours, best_contour, bgr_scaled (if debug=True)
    """
    H0, W0 = bgr.shape[:2]
    scale = 1.0
    if max(H0, W0) > max_side:
        scale = max_side / float(max(H0, W0))
        bgr_s = cv2.resize(bgr, (int(W0*scale), int(H0*scale)), interpolation=cv2.INTER_AREA)
    else:
        bgr_s = bgr

    gray = cv2.cvtColor(bgr_s, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Threshold to separate white background from board
    # The board should be darker than the white background
    # Use adaptive threshold or Otsu's method to find the board
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Alternatively, use a fixed threshold if Otsu doesn't work well
    # Since background is white, anything below ~200-220 should be the board
    # Try Otsu first, but if it doesn't capture the board well, use fixed threshold
    if np.sum(thresh) < 0.05 * thresh.size:  # Too little detected, try fixed threshold
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    
    # Clean up the thresholded image
    kernel = np.ones((5, 5), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # Find contours of non-white regions (the board)
    cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        debug_info = {"thresholded": thresh, "contours": [], "best_contour": None, "bgr_scaled": bgr_s} if debug else None
        return None, scale, debug_info

    # Find the largest contour (should be the board)
    largest_contour = max(cnts, key=cv2.contourArea)
    area = cv2.contourArea(largest_contour)
    
    # Check if the area is reasonable (at least 5% of image)
    if area < 0.05 * (H0 * W0 * scale * scale):
        debug_info = {"thresholded": thresh, "contours": cnts, "best_contour": None, "bgr_scaled": bgr_s} if debug else None
        return None, scale, debug_info
    
    # Approximate the contour to a quad
    peri = cv2.arcLength(largest_contour, True)
    approx = cv2.approxPolyDP(largest_contour, 0.02 * peri, True)
    
    # If we don't have 4 points, try a tighter approximation or use bounding rect
    if len(approx) < 4:
        # Try tighter approximation
        approx = cv2.approxPolyDP(largest_contour, 0.01 * peri, True)
        if len(approx) < 4:
            # Use bounding rectangle corners as fallback
            rect = cv2.minAreaRect(largest_contour)
            box = cv2.boxPoints(rect)
            approx = np.int0(box)
    
    # Ensure we have exactly 4 points
    if len(approx) > 4:
        # If we have more than 4 points, try to simplify further
        approx = cv2.approxPolyDP(largest_contour, 0.03 * peri, True)
        if len(approx) > 4:
            # Use convex hull and approximate that
            hull = cv2.convexHull(largest_contour)
            approx = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True)
    
    if len(approx) != 4:
        debug_info = {"thresholded": thresh, "contours": cnts, "best_contour": None, "bgr_scaled": bgr_s} if debug else None
        return None, scale, debug_info
    
    # Order the quad points
    quad_ordered = _order_quad(approx.reshape(4, 2).astype(np.float32))
    
    # Rescale to original coordinates
    quad = quad_ordered / scale
    
    best_contour_scaled = (largest_contour / scale).astype(np.float32) if debug else None
    debug_info = {"thresholded": thresh, "contours": cnts, "best_contour": best_contour_scaled, "bgr_scaled": bgr_s, "scale": scale} if debug else None
    return quad.astype(np.float32), scale, debug_info

# ---- Orientation: choose rotation with strongest checker contrast ----
def orient_warp_checker(warped: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    S = warped.shape[0] // GRID_SIZE  # Square size in 10x10 grid
    def score(img):
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Only score the inner 8x8 playing area (skip border: rows/cols 1-8 in 0-indexed, or 1-8 in 1-indexed)
        means = np.zeros((PLAYING_SIZE, PLAYING_SIZE), np.float32)
        for r in range(PLAYING_SIZE):
            for c in range(PLAYING_SIZE):
                # Skip border: start from index 1 (second square)
                y0, y1 = (r+1)*S, (r+2)*S
                x0, x1 = (c+1)*S, (c+2)*S
                means[r,c] = np.mean(g[y0:y1, x0:x1])
        # try both parities; pick larger light-dark gap
        mask0 = (np.add.outer(np.arange(PLAYING_SIZE), np.arange(PLAYING_SIZE)) & 1) == 0
        m0 = means[mask0].mean() - means[~mask0].mean()
        m1 = means[~mask0].mean() - means[mask0].mean()
        return max(abs(m0), abs(m1))
    best_k, best_val = 0, -1
    img = warped
    for k in range(4):
        val = score(img)
        if val > best_val:
            best_k, best_val = k, val
        img = np.rot90(img)  # rotates counterclockwise
    return np.ascontiguousarray(np.rot90(warped, k=best_k))

# ---- Split into tiles ----
def split_tiles(warped: np.ndarray, tile_px: int = TILE_PX, inset_frac: float = INSET_FRAC, expand_frac: float = EXPAND_FRAC) -> List[np.ndarray]:
    """
    Split warped image into tiles. The warped image is 10x10 grid (including border).
    We only extract the inner 8x8 playing area (skip the border squares).
    Each square is expanded to include surrounding space for pieces that extend beyond boundaries.
    """
    H, W = warped.shape[:2]
    S = H // GRID_SIZE  # Square size in 10x10 grid
    inset = int(round(S * inset_frac))
    expand = int(round(S * expand_frac))  # Amount to expand into surrounding squares
    tiles = []
    # Extract only the inner 8x8 playing area (skip border: indices 1-8 in 0-indexed)
    for r in range(PLAYING_SIZE):
        for c in range(PLAYING_SIZE):
            # Calculate base square boundaries (skip border: start from index 1)
            base_y0 = (r+1)*S + inset
            base_y1 = (r+2)*S - inset
            base_x0 = (c+1)*S + inset
            base_x1 = (c+2)*S - inset
            
            # Expand outward to include surrounding space
            y0 = max(0, base_y0 - expand)
            y1 = min(H, base_y1 + expand)
            x0 = max(0, base_x0 - expand)
            x1 = min(W, base_x1 + expand)
            
            crop = warped[y0:y1, x0:x1]
            if tile_px:
                crop = cv2.resize(crop, (tile_px, tile_px), interpolation=cv2.INTER_AREA)
            tiles.append(crop)
    return tiles  # length 64, row-major, a8..h1 after orientation

# ---- TFLite inference (13 classes) ----
class PieceClassifier:
    def __init__(self, model_path: str, num_threads: int = 2):
        assert tflite is not None, "Install tflite-runtime for Python testing"
        self.interp = tflite.Interpreter(model_path=model_path, num_threads=num_threads)
        self.interp.allocate_tensors()
        self.inp = self.interp.get_input_details()[0]
        self.out = self.interp.get_output_details()[0]
        self.h, self.w = self.inp["shape"][1], self.inp["shape"][2]
        self.is_float = self.inp["dtype"] == np.float32

    def _prep(self, tile: np.ndarray) -> np.ndarray:
        img = cv2.cvtColor(tile, cv2.COLOR_BGR2RGB)
        if img.shape[0] != self.h or img.shape[1] != self.w:
            img = cv2.resize(img, (self.w, self.h), interpolation=cv2.INTER_AREA)
        if self.is_float:
            img = img.astype(np.float32) / 255.0
        else:
            img = img.astype(np.uint8)
        return img

    def predict_batch(self, tiles: List[np.ndarray]) -> np.ndarray:
        n = len(tiles)
        preds = np.zeros((n,), dtype=np.int32)
        for i, t in enumerate(tiles):
            x = self._prep(t)
            x = np.expand_dims(x, axis=0)
            self.interp.set_tensor(self.inp["index"], x)
            self.interp.invoke()
            y = self.interp.get_tensor(self.out["index"]).squeeze()
            preds[i] = int(np.argmax(y))
        return preds  # indices 0..12

# ---- FEN + change detection ----
def to_fen(labels_64: np.ndarray) -> str:
    rows = []
    for r in range(8):
        row = []
        empty = 0
        for c in range(8):
            idx = int(labels_64[r*8 + c])
            ch = IDX_TO_FEN[idx]
            if ch == "":
                empty += 1
            else:
                if empty: row.append(str(empty)); empty = 0
                row.append(ch)
        if empty: row.append(str(empty))
        rows.append("".join(row))
    # Side to move 'w', no castling/en passant by vision here
    return "/".join(rows) + " w - - 0 1"

def boards_equal(a: np.ndarray, b: np.ndarray) -> bool:
    return a.shape == b.shape and np.array_equal(a, b)

# ---- Main per-image entry ----
def detect_classify(image_bgr: np.ndarray,
                    classifier: Optional[PieceClassifier]=None) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[str]]:
    quad, scale, _ = find_board_quad_fast(image_bgr, max_side=MAX_RESIZE, debug=False)
    if quad is None:
        return None, None, None
    warped, H = _four_point_warp(image_bgr, quad, size=WARP_SIZE)
    warped = orient_warp_checker(warped)
    tiles = split_tiles(warped, tile_px=TILE_PX, inset_frac=INSET_FRAC)
    if classifier is None:
        return warped, None, None
    labels = classifier.predict_batch(tiles)  # length 64
    fen = to_fen(labels.reshape(-1))
    return warped, labels.reshape(8,8), fen

# ---- Example change+POST loop (desktop test) ----
def process_and_maybe_send(image_path: str,
                           model_path: str,
                           backend_url: str,
                           device_id: str = "dev01",
                           stabilization_frames: int = 2):
    img = cv2.imread(image_path)
    clf = PieceClassifier(model_path, num_threads=2)
    prev = None
    stable = 0
    warped, labels, fen = detect_classify(img, clf)
    if labels is None:
        print("Board not found")
        return
    if prev is None or not boards_equal(prev, labels):
        stable = 1
        prev = labels.copy()
    else:
        stable += 1
    if stable >= stabilization_frames:
        payload = {
            "device": device_id,
            "fen": fen,
            "squares": [CLASS_NAMES[int(x)] for x in labels.reshape(-1)],
            "ts": int(time.time())
        }
        if requests is None:
            print("POST:", json.dumps(payload))
        else:
            try:
                r = requests.post(backend_url, json=payload, timeout=2.0)
                print("POST status:", r.status_code)
            except Exception as e:
                print("POST failed:", e)


# ---- Main function to process images from data folder ----
def main(debug: bool = False, max_images: Optional[int] = None, tiles_output_folder: Optional[str] = None):
    """
    Read images from data folder, crop to chess board, split into 64 squares, and save to output folder.
    
    Args:
        debug: If True, save intermediate debug images (edges, contours, corners overlay, etc.)
        max_images: Maximum number of images to process (None = process all)
        tiles_output_folder: Custom folder for saving tiles (None = save in output/{base_name}_tiles)
    """
    # data_folder = "data"
    data_folder = "data_top_down"
    output_folder = "output"
    
    # Clean output folder from previous runs
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)
        print(f"Cleaned existing output folder: {output_folder}")
    
    # Create fresh output folder
    os.makedirs(output_folder, exist_ok=True)
    
    # Find all image files in data folder
    image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.tiff', '*.tif']
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(data_folder, ext)))
        image_files.extend(glob.glob(os.path.join(data_folder, ext.upper())))
    
    if not image_files:
        print(f"No image files found in {data_folder} folder")
        return
    
    # Limit number of images if max_images is specified
    total_images = len(image_files)
    if max_images is not None and max_images > 0:
        image_files = image_files[:max_images]
        print(f"Found {total_images} image(s), processing first {len(image_files)} image(s)")
    else:
        print(f"Found {len(image_files)} image(s) to process")
    
    if debug:
        print("Debug mode: Intermediate images will be saved")
    
    successful_detections = 0
    total_processed = 0
    
    for img_path in image_files:
        print(f"\nProcessing: {img_path}")
        
        # Read image
        image_bgr = cv2.imread(img_path)
        if image_bgr is None:
            print(f"  Failed to read image: {img_path}")
            continue
        
        total_processed += 1
        
        # Get base filename without extension
        base_name = os.path.splitext(os.path.basename(img_path))[0]
        debug_folder = os.path.join(output_folder, f"{base_name}_debug") if debug else None
        
        if debug:
            os.makedirs(debug_folder, exist_ok=True)
            # Save original image
            cv2.imwrite(os.path.join(debug_folder, "00_original.jpg"), image_bgr)
        
        # Find chess board
        quad, scale, debug_info = find_board_quad_fast(image_bgr, max_side=MAX_RESIZE, debug=debug)
        if quad is None:
            print(f"  Could not detect chess board in: {img_path}")
            if debug and debug_info:
                # Save thresholded image even if no board found
                thresh_colored = cv2.cvtColor(debug_info["thresholded"], cv2.COLOR_GRAY2BGR)
                cv2.imwrite(os.path.join(debug_folder, "01_thresholded.jpg"), thresh_colored)
                # Save contours overlay
                contours_img = debug_info["bgr_scaled"].copy()
                cv2.drawContours(contours_img, debug_info["contours"], -1, (0, 255, 0), 2)
                cv2.imwrite(os.path.join(debug_folder, "02_all_contours.jpg"), contours_img)
            continue
        
        successful_detections += 1
        
        # Save debug images
        if debug and debug_info:
            # Save thresholded image
            thresh_colored = cv2.cvtColor(debug_info["thresholded"], cv2.COLOR_GRAY2BGR)
            cv2.imwrite(os.path.join(debug_folder, "01_thresholded.jpg"), thresh_colored)
            
            # Save all contours overlay
            contours_img = debug_info["bgr_scaled"].copy()
            cv2.drawContours(contours_img, debug_info["contours"], -1, (0, 255, 0), 2)
            cv2.imwrite(os.path.join(debug_folder, "02_all_contours.jpg"), contours_img)
            
            # Save best contour overlay
            if debug_info["best_contour"] is not None:
                best_contour_img = image_bgr.copy()
                best_contour_int = debug_info["best_contour"].astype(np.int32)
                cv2.drawContours(best_contour_img, [best_contour_int], -1, (0, 255, 0), 3)
                cv2.imwrite(os.path.join(debug_folder, "03_best_contour.jpg"), best_contour_img)
            
            # Save corners overlay on original image
            corners_img = image_bgr.copy()
            quad_int = quad.astype(np.int32)
            # Draw quad lines
            cv2.line(corners_img, tuple(quad_int[0]), tuple(quad_int[1]), (0, 255, 0), 3)
            cv2.line(corners_img, tuple(quad_int[1]), tuple(quad_int[2]), (0, 255, 0), 3)
            cv2.line(corners_img, tuple(quad_int[2]), tuple(quad_int[3]), (0, 255, 0), 3)
            cv2.line(corners_img, tuple(quad_int[3]), tuple(quad_int[0]), (0, 255, 0), 3)
            # Draw corners
            for i, corner in enumerate(quad_int):
                cv2.circle(corners_img, tuple(corner), 10, (0, 0, 255), -1)
                cv2.putText(corners_img, str(i), tuple(corner + 15), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imwrite(os.path.join(debug_folder, "04_corners_overlay.jpg"), corners_img)
        
        # Warp/crop to chess board
        warped, H = _four_point_warp(image_bgr, quad, size=WARP_SIZE)
        
        if debug:
            # Save warped board before orientation
            cv2.imwrite(os.path.join(debug_folder, "05_warped_before_orientation.jpg"), warped)
        
        warped = orient_warp_checker(warped)
        
        if debug:
            # Save warped board after orientation
            cv2.imwrite(os.path.join(debug_folder, "06_warped_after_orientation.jpg"), warped)
        
        # Split into 64 tiles
        tiles = split_tiles(warped, tile_px=TILE_PX, inset_frac=INSET_FRAC)
        
        # Save warped board
        warped_path = os.path.join(output_folder, f"{base_name}_board.jpg")
        cv2.imwrite(warped_path, warped)
        print(f"  Saved warped board: {warped_path}")
        
        # Save all 64 tiles
        if tiles_output_folder:
            # Use custom tiles output folder
            tiles_folder = tiles_output_folder
            os.makedirs(tiles_folder, exist_ok=True)
        else:
            # Use default location: output/{base_name}_tiles
            tiles_folder = os.path.join(output_folder, f"{base_name}_tiles")
            os.makedirs(tiles_folder, exist_ok=True)
        
        # Chess board notation: rows are 8-1, columns are a-h
        rows = ['8', '7', '6', '5', '4', '3', '2', '1']
        cols = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
        
        for idx, tile in enumerate(tiles):
            row = idx // 8
            col = idx % 8
            square_name = f"{cols[col]}{rows[row]}"
            # If using custom folder, prefix filename with base_name to avoid conflicts
            if tiles_output_folder:
                tile_filename = f"{base_name}_{square_name}.jpg"
                preview_filename = f"{base_name}_{square_name}_preview.jpg"
            else:
                tile_filename = f"{square_name}.jpg"
                preview_filename = f"{square_name}_preview.jpg"
            tile_path = os.path.join(tiles_folder, tile_filename)
            cv2.imwrite(tile_path, tile)
            
            # Save preview version (larger size for easier labeling)
            preview_path = os.path.join(tiles_folder, preview_filename)
            # Resize to larger size for preview (3x the original tile size, minimum 288px)
            if TILE_PX:
                preview_size = TILE_PX * 3
            else:
                # If tiles weren't resized, use 3x the current tile size or minimum 288px
                current_size = max(tile.shape[0], tile.shape[1])
                preview_size = max(current_size * 3, 288)
            preview_tile = cv2.resize(tile, (preview_size, preview_size), interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(preview_path, preview_tile)
        
        print(f"  Saved 64 tiles and 64 preview tiles to: {tiles_folder}")
        if debug:
            print(f"  Saved debug images to: {debug_folder}")
    
    print(f"\nProcessing complete! Output saved to {output_folder} folder")
    print(f"Detection summary: {successful_detections} out of {total_processed} image(s) successfully detected")


if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Process chess board images")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug mode (save intermediate images)")
    parser.add_argument("--max-images", "--max", type=int, default=None, 
                       help="Maximum number of images to process (default: process all)")
    parser.add_argument("--tiles-folder", "--tiles", type=str, default=None,
                       help="Custom folder for saving tiles (default: output/{base_name}_tiles)")
    
    args = parser.parse_args()
    
    main(debug=args.debug, max_images=args.max_images, tiles_output_folder=args.tiles_folder)
