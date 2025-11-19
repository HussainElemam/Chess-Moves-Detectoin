#!/usr/bin/env python3
"""
Interactive image organizer for chess piece training data.
Shows images one by one and moves them to appropriate folders based on keyboard input.
"""

import cv2
import os
import shutil
from pathlib import Path
import time

# Mapping of two-letter combinations to folder names
# Format: color + piece (e.g., 'wk' = white king, 'bk' = black king)
KEY_TO_FOLDER = {
    'e': 'empty',      # 'e' for empty square
    'wp': 'P',         # white pawn
    'bp': 'p',         # black pawn
    'wn': 'N',         # white knight
    'bn': 'n',         # black knight
    'wb': 'B',         # white bishop
    'bb': 'b',         # black bishop
    'wr': 'R',         # white rook
    'br': 'r',         # black rook
    'wq': 'Q',         # white queen
    'bq': 'q',         # black queen
    'wk': 'K',         # white king
    'bk': 'k',         # black king
    'i': None          # ignore - don't move
}

# Base directories
TRAINING_DATA_DIR = Path('tiles_images')
OUTPUT_BASE_DIR = Path('training_data')

def create_folders():
    """Create all necessary folders if they don't exist."""
    for folder_name in KEY_TO_FOLDER.values():
        if folder_name:  # Skip None (ignore case)
            folder_path = OUTPUT_BASE_DIR / folder_name
            folder_path.mkdir(parents=True, exist_ok=True)
            print(f"Created/verified folder: {folder_path}")

def get_image_files():
    """Get all image files from training_data folder, excluding _preview files."""
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
    image_files = []
    
    for ext in image_extensions:
        image_files.extend(TRAINING_DATA_DIR.glob(f'*{ext}'))
        image_files.extend(TRAINING_DATA_DIR.glob(f'*{ext.upper()}'))
    
    # Filter out _preview files (we only want originals to process)
    image_files = [f for f in image_files if '_preview' not in f.stem]
    
    # Sort for consistent ordering
    return sorted(image_files)

def get_preview_path(original_path):
    """Get the preview version path for an original image."""
    # Create preview filename: original_name_preview.extension
    preview_name = f"{original_path.stem}_preview{original_path.suffix}"
    preview_path = original_path.parent / preview_name
    return preview_path if preview_path.exists() else None

def display_image(original_path):
    """Display image in a window. Uses preview version if available, otherwise original."""
    # Try to use preview version first
    preview_path = get_preview_path(original_path)
    display_path = preview_path if preview_path else original_path
    
    img = cv2.imread(str(display_path))
    if img is None:
        print(f"Error: Could not load image {display_path}")
        return False
    
    # Resize if too large (for display purposes)
    max_display_size = 800
    height, width = img.shape[:2]
    if max(height, width) > max_display_size:
        scale = max_display_size / max(height, width)
        new_width = int(width * scale)
        new_height = int(height * scale)
        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
    
    # Display image without any text overlay
    cv2.imshow('Chess Piece Classifier', img)
    return True

def get_key_sequence(timeout_seconds=2.0):
    """
    Get a sequence of key presses from the user.
    Returns the key sequence as a string (e.g., 'wk', 'bk', 'e', 'i').
    Single character keys (e, i) are returned immediately.
    Two-character keys wait for the second character with a timeout.
    """
    # Wait for first key press (blocking)
    key = cv2.waitKey(0) & 0xFF
    
    if key == 27:  # Escape key
        return '\x1b'
    
    char = chr(key).lower()
    
    # Single character commands (e, i) return immediately
    if char in ['e', 'i']:
        return char
    
    # First character of a two-letter sequence
    if char in ['w', 'b']:
        sequence = char
        print(f"  First key: {char} - waiting for piece type (p/n/b/r/q/k)...", end='', flush=True)
        start_time = time.time()
        
        # Wait for second character with timeout
        while True:
            key = cv2.waitKey(1) & 0xFF
            
            if key != 255:  # A key was pressed
                if key == 27:  # Escape key
                    print()  # New line after the prompt
                    return '\x1b'
                
                second_char = chr(key).lower()
                if second_char in ['p', 'n', 'b', 'r', 'q', 'k']:
                    sequence += second_char
                    print(f"\n  Complete: {sequence}")
                    return sequence
                else:
                    print(f"\n  Invalid piece type '{second_char}'. Expected: p, n, b, r, q, or k")
                    return sequence  # Return partial (will be invalid)
            
            # Check timeout
            if (time.time() - start_time) > timeout_seconds:
                print(f"\n  Timeout - got '{sequence}', expected two characters")
                return sequence  # Return partial sequence (will be invalid)
            
            # Small delay to prevent high CPU usage
            time.sleep(0.01)
    else:
        # Invalid first character
        return char

def move_image(original_path, target_folder):
    """Move original image (and preview if exists) to target folder."""
    if target_folder is None:
        return False  # Ignore case
    
    target_dir = OUTPUT_BASE_DIR / target_folder
    target_path = target_dir / original_path.name
    
    try:
        # Get preview path BEFORE moving original (so we know where it is)
        preview_path = get_preview_path(original_path)
        
        # Move original file
        shutil.move(str(original_path), str(target_path))
        print(f"Moved {original_path.name} -> {target_folder}/")
        
        # Also move preview if it exists
        if preview_path:
            preview_target = target_dir / preview_path.name
            shutil.move(str(preview_path), str(preview_target))
            print(f"Moved {preview_path.name} -> {target_folder}/")
        
        return True
    except Exception as e:
        print(f"Error moving {original_path.name}: {e}")
        return False

def main():
    """Main function to organize images."""
    print("Chess Piece Training Data Organizer")
    print("=" * 50)
    
    # Check if training_data directory exists
    if not TRAINING_DATA_DIR.exists():
        print(f"Error: {TRAINING_DATA_DIR} directory not found!")
        return
    
    # Create output folders
    create_folders()
    
    # Get all image files
    image_files = get_image_files()
    
    if not image_files:
        print(f"No image files found in {TRAINING_DATA_DIR}")
        return
    
    # Filter to only images in root of training_data (not in subfolders)
    root_images = [f for f in image_files if f.parent == TRAINING_DATA_DIR]
    
    if not root_images:
        print("No images found in root of training_data directory (all may already be organized)")
        cv2.destroyAllWindows()
        return
    
    print(f"\nFound {len(root_images)} images to process")
    print("\nKey combinations:")
    print("  Empty square: 'e'")
    print("  White pieces: 'w' + piece (wp=pawn, wn=knight, wb=bishop, wr=rook, wq=queen, wk=king)")
    print("  Black pieces: 'b' + piece (bp=pawn, bn=knight, bb=bishop, br=rook, bq=queen, bk=king)")
    print("  Ignore: 'i'")
    print("  Quit: 'Esc'\n")
    
    # Process each image
    processed = 0
    ignored = 0
    idx = 0
    
    while idx < len(root_images):
        image_path = root_images[idx]
        
        # Display image
        if not display_image(image_path):
            idx += 1
            continue
        
        # Wait for key sequence
        print(f"[{idx + 1}/{len(root_images)}] {image_path.name} - Press key(s) to classify...")
        
        # Get key sequence (handles both single and two-character inputs)
        key_sequence = get_key_sequence()
        
        # Handle key sequence
        if key_sequence == '\x1b':  # Escape key
            print("\nQuitting...")
            break
        elif key_sequence == 'i':
            print(f"Ignored: {image_path.name}")
            ignored += 1
            idx += 1
        elif key_sequence in KEY_TO_FOLDER:
            folder_name = KEY_TO_FOLDER[key_sequence]
            if move_image(image_path, folder_name):
                processed += 1
            idx += 1
        else:
            valid_keys = ', '.join(sorted([k for k in KEY_TO_FOLDER.keys() if k != 'i']))
            print(f"Invalid key sequence '{key_sequence}'. Valid: {valid_keys}, i (ignore), Esc (quit)")
            # Don't advance, show same image again by not incrementing idx
    
    cv2.destroyAllWindows()
    
    print("\n" + "=" * 50)
    print(f"Processing complete!")
    print(f"  Processed: {processed}")
    print(f"  Ignored: {ignored}")
    print(f"  Remaining: {len(root_images) - processed - ignored}")

if __name__ == '__main__':
    main()

