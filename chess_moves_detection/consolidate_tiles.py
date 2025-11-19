#!/usr/bin/env python3
"""
Script to consolidate all tile images from output/*_tiles directories
into a single tiles_images directory.
"""

import os
import shutil
from pathlib import Path


def consolidate_tiles():
    """Move all tile images from output/*_tiles to tiles_images directory."""
    
    # Define paths
    project_root = Path(__file__).parent
    output_dir = project_root / "output"
    tiles_images_dir = project_root / "tiles_images"
    
    # Create tiles_images directory if it doesn't exist
    tiles_images_dir.mkdir(exist_ok=True)
    
    # Find all *_tiles directories
    tiles_dirs = sorted(output_dir.glob("*_tiles"))
    
    if not tiles_dirs:
        print("No *_tiles directories found in output/")
        return
    
    print(f"Found {len(tiles_dirs)} tile directories")
    
    total_moved = 0
    
    # Process each tiles directory
    for tiles_dir in tiles_dirs:
        if not tiles_dir.is_dir():
            continue
        
        # Get the directory name (e.g., "1_tiles" -> "1")
        dir_name = tiles_dir.stem.replace("_tiles", "")
        
        # Find all .jpg files in this directory
        image_files = list(tiles_dir.glob("*.jpg"))
        
        print(f"Processing {tiles_dir.name}: {len(image_files)} images")
        
        # Move each image file
        for image_file in image_files:
            # Create new filename with prefix to avoid conflicts
            # e.g., "1_tiles_a1.jpg" or "1_tiles_a1_preview.jpg"
            new_filename = f"{dir_name}_{image_file.name}"
            dest_path = tiles_images_dir / new_filename
            
            # Move the file
            shutil.move(str(image_file), str(dest_path))
            total_moved += 1
    
    print(f"\nDone! Moved {total_moved} images to {tiles_images_dir}")


if __name__ == "__main__":
    consolidate_tiles()

