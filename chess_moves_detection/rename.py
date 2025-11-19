import os

# Set the directory containing your images
directory = 'data_top_down'

# Get all image files (common extensions)
image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
images = [f for f in os.listdir(directory) if f.lower().endswith(image_extensions)]

# Sort the files alphabetically to ensure consistent ordering
images.sort()

# Rename each image to a numbered sequence
for i, filename in enumerate(images, start=1):
    ext = os.path.splitext(filename)[1]
    new_name = f"{i}{ext}"
    old_path = os.path.join(directory, filename)
    new_path = os.path.join(directory, new_name)
    os.rename(old_path, new_path)
    print(f"Renamed: {filename} → {new_name}")

print("Renaming complete.")
