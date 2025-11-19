#!/usr/bin/env python3
"""
Separate preview files into a separate folder.
Moves all files with '_preview' in their name to a dedicated previews folder.
"""

import shutil
from pathlib import Path

# Base directory
TRAINING_DATA_DIR = Path('training_data')
PREVIEWS_DIR = TRAINING_DATA_DIR / 'previews'

def find_preview_files():
    """Find all preview files in training_data directory and subfolders."""
    preview_files = []
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
    
    # Search in training_data and all subdirectories
    for ext in image_extensions:
        # Search in root
        preview_files.extend(TRAINING_DATA_DIR.glob(f'*_preview{ext}'))
        preview_files.extend(TRAINING_DATA_DIR.glob(f'*_preview{ext.upper()}'))
        
        # Search in subdirectories
        for subdir in TRAINING_DATA_DIR.iterdir():
            if subdir.is_dir() and subdir.name != 'previews':
                preview_files.extend(subdir.glob(f'*_preview{ext}'))
                preview_files.extend(subdir.glob(f'*_preview{ext.upper()}'))
    
    return sorted(preview_files)

def organize_preview(preview_path):
    """Move preview file to previews folder, maintaining subfolder structure."""
    # Get relative path from training_data
    try:
        relative_path = preview_path.relative_to(TRAINING_DATA_DIR)
    except ValueError:
        # If file is not in training_data, skip it
        return False
    
    # If preview is in a subfolder, maintain that structure in previews folder
    if len(relative_path.parts) > 1:
        # Preview is in a subfolder (e.g., training_data/p/image_preview.jpg)
        subfolder = relative_path.parts[0]  # Get the subfolder name (e.g., 'p')
        target_dir = PREVIEWS_DIR / subfolder
    else:
        # Preview is in root of training_data
        target_dir = PREVIEWS_DIR
    
    # Create target directory if it doesn't exist
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Move the file
    target_path = target_dir / preview_path.name
    
    try:
        shutil.move(str(preview_path), str(target_path))
        return True
    except Exception as e:
        print(f"Error moving {preview_path}: {e}")
        return False

def main():
    """Main function to separate preview files."""
    print("Preview File Separator")
    print("=" * 50)
    
    # Check if training_data directory exists
    if not TRAINING_DATA_DIR.exists():
        print(f"Error: {TRAINING_DATA_DIR} directory not found!")
        return
    
    # Create previews directory
    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Created/verified previews directory: {PREVIEWS_DIR}\n")
    
    # Find all preview files
    preview_files = find_preview_files()
    
    if not preview_files:
        print("No preview files found!")
        return
    
    print(f"Found {len(preview_files)} preview files to move\n")
    
    # Move each preview file
    moved = 0
    failed = 0
    
    for preview_path in preview_files:
        # Get the relative path for display
        try:
            display_path = preview_path.relative_to(TRAINING_DATA_DIR)
        except ValueError:
            display_path = preview_path
        
        if organize_preview(preview_path):
            print(f"Moved: {display_path}")
            moved += 1
        else:
            print(f"Failed: {display_path}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Separation complete!")
    print(f"  Moved: {moved}")
    print(f"  Failed: {failed}")
    print(f"\nPreview files are now in: {PREVIEWS_DIR}")

if __name__ == '__main__':
    main()

