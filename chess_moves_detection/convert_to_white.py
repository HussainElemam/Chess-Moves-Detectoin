#!/usr/bin/env python3
"""
Convert black pieces to white pieces.
Goes through black piece folders and allows moving images to white equivalent folders.
"""

import cv2
import shutil
from pathlib import Path

# Mapping of black piece folders to white piece folders
BLACK_TO_WHITE = {
    'p': 'P',
    'n': 'N',
    'b': 'B',
    'r': 'R',
    'q': 'Q',
    'k': 'K'
}

# Base directory
TRAINING_DATA_DIR = Path('training_data')

def get_preview_path(original_path):
    """Get the preview version path for an original image."""
    preview_name = f"{original_path.stem}_preview{original_path.suffix}"
    preview_path = original_path.parent / preview_name
    return preview_path if preview_path.exists() else None

def display_image(image_path):
    """Display image in a window. Uses preview version if available, otherwise original."""
    # Try to use preview version first
    preview_path = get_preview_path(image_path)
    display_path = preview_path if preview_path else image_path
    
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
    cv2.imshow('Convert to White', img)
    return True

def move_to_white(black_folder, image_path):
    """Move image from black folder to white folder."""
    white_folder = BLACK_TO_WHITE[black_folder]
    black_dir = TRAINING_DATA_DIR / black_folder
    white_dir = TRAINING_DATA_DIR / white_folder
    
    # Create white folder if it doesn't exist
    white_dir.mkdir(parents=True, exist_ok=True)
    
    # Move original file
    white_target = white_dir / image_path.name
    try:
        shutil.move(str(image_path), str(white_target))
        print(f"Moved {image_path.name} -> {white_folder}/")
        
        # Also move preview if it exists
        preview_path = get_preview_path(image_path)
        if preview_path and preview_path.exists():
            preview_target = white_dir / preview_path.name
            shutil.move(str(preview_path), str(preview_target))
            print(f"Moved {preview_path.name} -> {white_folder}/")
        
        return True
    except Exception as e:
        print(f"Error moving {image_path.name}: {e}")
        return False

def process_folder(black_folder):
    """Process all images in a black piece folder."""
    folder_path = TRAINING_DATA_DIR / black_folder
    
    if not folder_path.exists():
        print(f"Folder {black_folder} does not exist, skipping...")
        return 0, 0
    
    # Get all image files (excluding preview files)
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
    image_files = []
    
    for ext in image_extensions:
        image_files.extend(folder_path.glob(f'*{ext}'))
        image_files.extend(folder_path.glob(f'*{ext.upper()}'))
    
    # Filter out _preview files
    image_files = [f for f in image_files if '_preview' not in f.stem]
    image_files = sorted(image_files)
    
    if not image_files:
        return 0, 0
    
    print(f"\nProcessing {black_folder}/ folder: {len(image_files)} images")
    print("Press 'w' to convert to white, 'n' for next (keep as black), 'Esc' to quit folder")
    
    converted = 0
    idx = 0
    
    while idx < len(image_files):
        image_path = image_files[idx]
        
        # Display image
        if not display_image(image_path):
            idx += 1
            continue
        
        # Wait for key press
        print(f"[{idx + 1}/{len(image_files)}] {image_path.name} - Press 'w' to convert to white, 'n' for next...")
        key = cv2.waitKey(0) & 0xFF
        
        # Handle key press
        if key == 27:  # Escape key
            print(f"\nQuitting {black_folder}/ folder...")
            break
        elif key == ord('w'):
            if move_to_white(black_folder, image_path):
                converted += 1
            idx += 1
        elif key == ord('n'):
            print(f"Skipped: {image_path.name} (staying as black)")
            idx += 1
        else:
            print(f"Invalid key. Press 'w' to convert to white, 'n' for next, 'Esc' to quit folder")
            # Don't advance, show same image again
    
    return converted, len(image_files)

def main():
    """Main function to convert black pieces to white."""
    print("Black to White Piece Converter")
    print("=" * 50)
    
    # Check if training_data directory exists
    if not TRAINING_DATA_DIR.exists():
        print(f"Error: {TRAINING_DATA_DIR} directory not found!")
        return
    
    total_converted = 0
    total_processed = 0
    
    # Process each black piece folder
    for black_folder in BLACK_TO_WHITE.keys():
        converted, processed = process_folder(black_folder)
        total_converted += converted
        total_processed += processed
    
    cv2.destroyAllWindows()
    
    print("\n" + "=" * 50)
    print(f"Conversion complete!")
    print(f"  Converted to white: {total_converted}")
    print(f"  Kept as black: {total_processed - total_converted}")

if __name__ == '__main__':
    main()

