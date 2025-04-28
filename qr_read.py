from pathlib import Path
import fitz  # PyMuPDF
import cv2
import numpy as np


def pdf_first_page_to_numpy(pdf_path: str | Path, dpi: int = 300) -> np.ndarray:
    """PDF 첫 페이지를 주어진 해상도(dpi)로 렌더링해 NumPy BGR 이미지 반환"""
    pdf_path = Path(pdf_path).expanduser()
    with fitz.open(pdf_path) as doc:
        page = doc.load_page(0)  # 0-based index → 첫 페이지
        # 확대 행렬 계산 (72 dpi × zoom = 원하는 dpi)
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)  # RGB
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        # OpenCV는 BGR을 선호 → 채널 순서 뒤집기
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def read_qr_from_pdf(pdf_path: str | Path, dpi: int = 300) -> str | None:
    """Poppler 없이 PDF 첫 페이지의 QR 값을 반환 (없으면 None)"""
    cv_img = pdf_first_page_to_numpy(pdf_path, dpi)
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(cv_img)
    return data or None


if __name__ == "__main__":
    target_pdf = "Katri.pdf"
    qr_text = read_qr_from_pdf(target_pdf)
    if qr_text:
        print("QR 코드 내용:", qr_text)
    else:
        print("QR 코드를 찾거나 디코딩하지 못했습니다.")
