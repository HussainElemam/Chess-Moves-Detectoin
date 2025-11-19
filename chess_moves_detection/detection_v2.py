# chess_mobile_fast.py
import cv2, numpy as np, time, json, os, glob
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
    Find chess board quad in image.
    Returns: (quad, scale, debug_info)
    debug_info contains: edges, contours, best_contour, bgr_scaled (if debug=True)
    """
    H0, W0 = bgr.shape[:2]
    scale = 1.0
    if max(H0, W0) > max_side:
        scale = max_side / float(max(H0, W0))
        bgr_s = cv2.resize(bgr, (int(W0*scale), int(H0*scale)), interpolation=cv2.INTER_AREA)
    else:
        bgr_s = bgr

    gray = cv2.cvtColor(bgr_s, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3,3), 0)
    edges = cv2.Canny(gray, CANNY[0], CANNY[1], L2gradient=True)
    edges = cv2.dilate(edges, np.ones((3,3), np.uint8), iterations=1)

    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        debug_info = {"edges": edges, "contours": [], "best_contour": None, "bgr_scaled": bgr_s} if debug else None
        return None, scale, debug_info

    # Pick the biggest near-square convex quad
    best, best_score = None, -1
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 0.02 * edges.size:  # skip tiny
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        # squareness score: opposite sides similar and rectangle-ish
        q = approx.reshape(4,2).astype(np.float32)
        q = _order_quad(q)
        s0 = np.linalg.norm(q[1]-q[0])  # top
        s1 = np.linalg.norm(q[2]-q[1])  # right
        s2 = np.linalg.norm(q[2]-q[3])  # bottom
        s3 = np.linalg.norm(q[3]-q[0])  # left
        opp_diff = abs(s0 - s2) + abs(s1 - s3)
        aspect = max(s0, s2) / max(1e-6, max(s1, s3))
        aspect_pen = abs(np.log(aspect))  # 0 if square
        score = area - 1000*opp_diff - 5000*aspect_pen
        if score > best_score:
            best, best_score = approx, score

    if best is None:
        debug_info = {"edges": edges, "contours": cnts, "best_contour": None, "bgr_scaled": bgr_s} if debug else None
        return None, scale, debug_info
    
    # rescale to original coordinates
    quad = best.reshape(4,2) / scale
    best_contour_scaled = (best / scale).astype(np.float32) if debug else None
    debug_info = {"edges": edges, "contours": cnts, "best_contour": best_contour_scaled, "bgr_scaled": bgr_s, "scale": scale} if debug else None
    return quad.astype(np.float32), scale, debug_info

# ---- Orientation: choose rotation with strongest checker contrast ----
def orient_warp_checker(warped: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    S = warped.shape[0] // 8
    def score(img):
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        means = np.zeros((8,8), np.float32)
        for r in range(8):
            for c in range(8):
                y0, y1 = r*S, (r+1)*S
                x0, x1 = c*S, (c+1)*S
                means[r,c] = np.mean(g[y0:y1, x0:x1])
        # try both parities; pick larger light-dark gap
        mask0 = (np.add.outer(np.arange(8), np.arange(8)) & 1) == 0
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
def split_tiles(warped: np.ndarray, tile_px: int = TILE_PX, inset_frac: float = INSET_FRAC) -> List[np.ndarray]:
    H = warped.shape[0]
    S = H // 8
    inset = int(round(S * inset_frac))
    tiles = []
    for r in range(8):
        for c in range(8):
            y0 = r*S + inset; y1 = (r+1)*S - inset
            x0 = c*S + inset; x1 = (c+1)*S - inset
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
def main(debug: bool = False):
    """
    Read images from data folder, crop to chess board, split into 64 squares, and save to output folder.
    
    Args:
        debug: If True, save intermediate debug images (edges, contours, corners overlay, etc.)
    """
    data_folder = "data"
    output_folder = "output"
    
    # Create output folder if it doesn't exist
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
    
    print(f"Found {len(image_files)} image(s) to process")
    if debug:
        print("Debug mode: Intermediate images will be saved")
    
    for img_path in image_files:
        print(f"\nProcessing: {img_path}")
        
        # Read image
        image_bgr = cv2.imread(img_path)
        if image_bgr is None:
            print(f"  Failed to read image: {img_path}")
            continue
        
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
                # Save edges even if no board found
                edges_colored = cv2.cvtColor(debug_info["edges"], cv2.COLOR_GRAY2BGR)
                cv2.imwrite(os.path.join(debug_folder, "01_edges.jpg"), edges_colored)
                # Save contours overlay
                contours_img = debug_info["bgr_scaled"].copy()
                cv2.drawContours(contours_img, debug_info["contours"], -1, (0, 255, 0), 2)
                cv2.imwrite(os.path.join(debug_folder, "02_all_contours.jpg"), contours_img)
            continue
        
        # Save debug images
        if debug and debug_info:
            # Save edges
            edges_colored = cv2.cvtColor(debug_info["edges"], cv2.COLOR_GRAY2BGR)
            cv2.imwrite(os.path.join(debug_folder, "01_edges.jpg"), edges_colored)
            
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
        tiles_folder = os.path.join(output_folder, f"{base_name}_tiles")
        os.makedirs(tiles_folder, exist_ok=True)
        
        # Chess board notation: rows are 8-1, columns are a-h
        rows = ['8', '7', '6', '5', '4', '3', '2', '1']
        cols = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
        
        for idx, tile in enumerate(tiles):
            row = idx // 8
            col = idx % 8
            square_name = f"{cols[col]}{rows[row]}"
            tile_path = os.path.join(tiles_folder, f"{square_name}.jpg")
            cv2.imwrite(tile_path, tile)
        
        print(f"  Saved 64 tiles to: {tiles_folder}")
        if debug:
            print(f"  Saved debug images to: {debug_folder}")
    
    print(f"\nProcessing complete! Output saved to {output_folder} folder")


if __name__ == "__main__":
    import sys
    # Check if debug mode is enabled via command line argument
    debug_mode = "--debug" in sys.argv or "-d" in sys.argv
    main(debug=debug_mode)
