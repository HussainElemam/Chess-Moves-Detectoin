#!/usr/bin/env python3
"""
Script to create training_data_preview folder that mirrors training_data structure
but uses preview images from tiles_images folder.
"""

import os
import shutil
from pathlib import Path


def create_training_data_preview():
    """
    Creates training_data_preview folder structure mirroring training_data,
    but using preview images from tiles_images.
    """
    # Define paths
    base_dir = Path(__file__).parent
    training_data_dir = base_dir / "training_data"
    tiles_images_dir = base_dir / "tiles_images"
    output_dir = base_dir / "training_data_preview"
    
    # Verify input directories exist
    if not training_data_dir.exists():
        print(f"Error: {training_data_dir} does not exist!")
        return
    
    if not tiles_images_dir.exists():
        print(f"Error: {tiles_images_dir} does not exist!")
        return
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(exist_ok=True)
    
    # Counters for statistics
    total_files = 0
    copied_files = 0
    missing_files = 0
    
    # Iterate through all class folders in training_data
    for class_folder in sorted(training_data_dir.iterdir()):
        if not class_folder.is_dir():
            continue
        
        class_name = class_folder.name
        print(f"Processing class: {class_name}")
        
        # Create corresponding class folder in output directory
        output_class_dir = output_dir / class_name
        output_class_dir.mkdir(exist_ok=True)
        
        # Process each image file in the class folder
        for image_file in sorted(class_folder.glob("*.jpg")):
            total_files += 1
            image_name = image_file.name  # e.g., "1_g4.jpg"
            
            # Construct preview image path in tiles_images
            # Remove .jpg extension, add _preview.jpg
            base_name = image_name.replace(".jpg", "")
            preview_name = f"{base_name}_preview.jpg"
            preview_path = tiles_images_dir / preview_name
            
            # Check if preview exists
            if not preview_path.exists():
                print(f"  Warning: Preview not found for {class_name}/{image_name}")
                missing_files += 1
                continue
            
            # Copy preview to output directory with original filename
            output_path = output_class_dir / image_name
            shutil.copy2(preview_path, output_path)
            copied_files += 1
        
        print(f"  Processed {len(list(class_folder.glob('*.jpg')))} files in {class_name}")
    
    # Print summary
    print("\n" + "="*50)
    print("Summary:")
    print(f"  Total files processed: {total_files}")
    print(f"  Successfully copied: {copied_files}")
    if missing_files > 0:
        print(f"  Missing previews: {missing_files}")
    print(f"  Output directory: {output_dir}")
    print("="*50)


if __name__ == "__main__":
    create_training_data_preview()


