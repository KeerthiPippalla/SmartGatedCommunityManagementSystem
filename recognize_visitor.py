import os
import numpy as np
import torch
from facenet_pytorch import MTCNN, InceptionResnetV1
from sklearn.metrics.pairwise import cosine_similarity
from PIL import Image
from firebase_admin import db

device = 'cpu'
detector = MTCNN(keep_all=False, device=device)
model = InceptionResnetV1(pretrained='vggface2').eval().to(device)

THRESHOLD = 0.65
FACE_DATA_DIR = "face_data"


def load_villa_data(villa_id):
    villa_path = os.path.join(FACE_DATA_DIR, villa_id)
    if not os.path.exists(villa_path):
        return None, None

    ids = np.load(os.path.join(villa_path, "visitor_ids.npy"), allow_pickle=True)
    embs = np.load(os.path.join(villa_path, "visitor_embeddings.npy"), allow_pickle=True)
    return ids, embs


def extract_embedding(image):
    face = detector(image)
    if face is None:
        return None

    if face.ndim == 3:
        face = face.unsqueeze(0)

    with torch.no_grad():
        emb = model(face.to(device)).cpu().numpy().flatten()
    return emb


def recognize_visitor(image_path, villa_id):
    visitor_ids, visitor_embeddings = load_villa_data(villa_id)

    img = Image.open(image_path).convert("RGB")
    emb = extract_embedding(img)

    if emb is None:
        return {"status": "unknown"}

    if visitor_embeddings is None:
        return {"status": "unknown"}

    sims = cosine_similarity([emb], visitor_embeddings)[0]
    best_idx = np.argmax(sims)
    best_score = sims[best_idx]
    if best_score >= THRESHOLD:
        visitor_id = visitor_ids[best_idx]

        visitor_ref = db.reference(f"villas/{villa_id}/visitors/{visitor_id}")
        visitor_data = visitor_ref.get()

        if visitor_data and "name" in visitor_data:
            visitor_name = visitor_data["name"]
        else:
            visitor_name = "KNOWN VISITOR"


        return {
            "status": "allowed",
            "visitor_id": visitor_id,
            "visitor_name": visitor_name,
            "villa_id": villa_id,
            "score": float(best_score)
        }
   
    else:
        return {"status": "unknown"}
