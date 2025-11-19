import os

# Ensure DATA_DIR is set correctly (e.g., "previews" or "previews_duplicated")
# DATA_DIR is defined in cell mBrERergalxR
DATA_DIR = 'previews'
print(f"Analyzing data in: {DATA_DIR}")

total_images = 0
class_counts = {}

# Loop through each class directory
for class_name in os.listdir(DATA_DIR):
    class_path = os.path.join(DATA_DIR, class_name)
    
    # Only process if it's a directory
    if os.path.isdir(class_path):
        image_count = 0
        # Count image files in the class directory
        for filename in os.listdir(class_path):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                image_count += 1
        
        class_counts[class_name] = image_count
        total_images += image_count

# Print summary
print("\n--- Data Summary ---")
for class_name, count in class_counts.items():
    print(f"Class '{class_name}': {count} images")
print(f"\nTotal images: {total_images}")