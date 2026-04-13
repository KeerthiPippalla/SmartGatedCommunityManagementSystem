import os
import numpy as np
from PIL import Image
from recognize_visitor import extract_embedding

FACE_DATA_DIR = "face_data"  

def register_new_visitor(villa_id, images, visitor_id):


    try:
        save_dir = os.path.join("data", "visitors", villa_id, visitor_id)
        os.makedirs(save_dir, exist_ok=True)

        embeddings = []

        count = 1
        for img in images:
            ext = os.path.splitext(img.filename)[1]
            filename = f"{visitor_id}_{count}{ext}"
            img_path = os.path.join(save_dir, filename)
            img.save(img_path)

            image = Image.open(img_path).convert("RGB")
            emb = extract_embedding(image)

            if emb is None:
                return False, "No face detected in one of the images"

            embeddings.append(emb)
            count += 1

        avg_embedding = np.mean(embeddings, axis=0)

        villa_face_dir = os.path.join(FACE_DATA_DIR, villa_id)
        os.makedirs(villa_face_dir, exist_ok=True)

        ids_path = os.path.join(villa_face_dir, "visitor_ids.npy")
        emb_path = os.path.join(villa_face_dir, "visitor_embeddings.npy")

        if os.path.exists(ids_path) and os.path.exists(emb_path):
            visitor_ids = np.load(ids_path, allow_pickle=True).tolist()
            visitor_embeddings = np.load(emb_path, allow_pickle=True)
        else:
            visitor_ids = []
            visitor_embeddings = np.empty((0, avg_embedding.shape[0]))

        visitor_ids.append(visitor_id)
        visitor_embeddings = np.vstack([visitor_embeddings, avg_embedding])

        np.save(ids_path, np.array(visitor_ids, dtype=object))
        np.save(emb_path, visitor_embeddings)

        return True, "Visitor registered and face data updated successfully"

    except Exception as e:
        print("Error in register_new_visitor:", e)
        return False, f"Registration failed: {str(e)}"