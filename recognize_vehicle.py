
import os
import cv2
import torch
import numpy as np
from ultralytics import YOLO

from models.model.LPRNet import build_lprnet
from models.data.load_data import CHARS



BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")

YOLO_PATH = os.path.join(MODELS_DIR, "yolo.pt")
LPR_PATH = os.path.join(MODELS_DIR, "lprnet.pth")


device = "cuda" if torch.cuda.is_available() else "cpu"
print("Using device:", device)

detector = YOLO(YOLO_PATH)

lprnet = build_lprnet(
    lpr_max_len=12,
    phase=False,
    class_num=len(CHARS),
    dropout_rate=0
)

lprnet.load_state_dict(torch.load(LPR_PATH, map_location=device))
lprnet = lprnet.to(device).eval()

print("Models loaded successfully")

def preprocess_plate(plate):
    plate = cv2.resize(plate, (94, 24))
    plate = plate.astype(np.float32)
    plate -= 127.5
    plate *= 0.0078125
    plate = np.transpose(plate, (2, 0, 1))
    return torch.from_numpy(plate).unsqueeze(0).to(device)

def decode(preds):
    blank = len(CHARS) - 1
    seq = preds.argmax(0)

    text = ""
    prev = -1

    for c in seq:
        if c != prev and c != blank:
            text += CHARS[c]
        prev = c

    return text

def recognize_vehicle(img_path):

    img = cv2.imread(img_path)

    if img is None:
        print("Image not found:", img_path)
        return None

    results = detector(img)[0]

    best_text = None
    best_area = 0

    for box in results.boxes.xyxy:

        x1, y1, x2, y2 = map(int, box)

        plate = img[y1:y2, x1:x2]
        if plate.size == 0:
            continue

        area = (x2 - x1) * (y2 - y1)
        if area < best_area:
            continue

        plate_tensor = preprocess_plate(plate)

        with torch.no_grad():
            preds = lprnet(plate_tensor)[0].cpu().numpy()

        text = decode(preds)

        best_area = area
        best_text = text

    if best_text:
        print("Detected Plate:", best_text)
        return best_text

    print("No plate detected")
    return None

