from pdf2image import convert_from_path
import os

def pdf_to_images(pdf_path, dpi=400):
    pages = convert_from_path(pdf_path, dpi=dpi)

    image_paths = []

    for i, page in enumerate(pages):
        image_path = os.path.join("temp_pages", f"page_{i+1}.png")

        if not os.path.exists("temp_pages"):
            os.makedirs("temp_pages")

        page.save(image_path, "PNG")
        image_paths.append(image_path)

    return image_paths