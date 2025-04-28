# -*- coding: utf-8 -*-
"""
Flask + Selenium : FITI 성적서 이미지 ZIP 다운로드 서버
=====================================================

* POST /fiti   ─ rcpt_1·2·3, doc_1·2·3 JSON → ZIP(페이지 PNG) 응답
* POST /kotiti ─ placeholder
* POST /katri  ─ placeholder
"""
from flask import Flask, request, send_file, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import io, zipfile, time, traceback, requests
import fitz
import cv2, numpy as np
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import re
from selenium.common.exceptions import TimeoutException

app = Flask(__name__)

# Common Const
FITI_URL = "https://www.fiti.re.kr/cs/contents/CS0401010000.do"
PNG_SCROLL_DELAY = 0.3     
GO_PDF_RE = re.compile(r"javascript:goPDF\('(.+?)(?:'|%27)", re.I) 

@app.route('/')
def health():
    return "server avaliable"

# ------------------------------------------------------------------------------------------------ FITI
# POST FITI
@app.route("/fiti", methods=["POST"])
def fiti():
    data = request.get_json(silent=True) or {}

    rcpt = [data.get(f"rcpt_{i}") for i in (1, 2, 3)]
    doc  = [data.get(f"doc_{i}")  for i in (1, 2, 3)]

    # Validate Input
    if any(v is None for v in (*rcpt, *doc)):
        return jsonify({"status": "error",
                        "message": "rcpt_1~3, doc_1~3 모든 값이 필요합니다."}), 400

    try:
        # 1) Every Request Open Driver → with 블록 종료 시 자동 quit
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")   # Headless
        with webdriver.Chrome(options=options) as driver:
            wait = WebDriverWait(driver, 10)

            # 2) Input value
            driver.get(FITI_URL)
            wait.until(EC.presence_of_element_located((By.ID, "receptionNumber_1")))

            driver.find_element(By.ID, "receptionNumber_1").send_keys(rcpt[0])
            driver.find_element(By.ID, "receptionNumber_2").send_keys(rcpt[1])
            driver.find_element(By.ID, "receptionNumber_3").send_keys(rcpt[2])

            driver.find_element(By.ID, "dcmntIdntyNumber_1").send_keys(doc[0])
            driver.find_element(By.ID, "dcmntIdntyNumber_2").send_keys(doc[1])
            driver.find_element(By.ID, "dcmntIdntyNumber_3").send_keys(doc[2])

            driver.find_element(By.CSS_SELECTOR, "div.btn_wrap a").click()
            wait.until(EC.number_of_windows_to_be(2))

            # 3) Open new tab
            WebDriverWait(driver, 5).until(EC.number_of_windows_to_be(2))
            handles = driver.window_handles
            if len(handles) < 2:
                raise RuntimeError("검증서 뷰어 탭이 열리지 않았습니다.")
            
            # 3) Get into Iframe
            _, new_tab = driver.window_handles
            driver.switch_to.window(new_tab)
            WebDriverWait(driver, 15).until(
                EC.frame_to_be_available_and_switch_to_it((By.ID, "viewerFrame"))
            )

            # 4) Build zip
            pages = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[id^='pageContainer']"))
            )

            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for idx, elem in enumerate(pages, 1):
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", elem)
                    time.sleep(PNG_SCROLL_DELAY)
                    zf.writestr(f"page_{idx}.png", elem.screenshot_as_png)

            zip_buf.seek(0)

        # 5) response
        return send_file(zip_buf,
                         as_attachment=True,
                         download_name="fiti_pages.zip",
                         mimetype="application/zip")

    except Exception:
        # loggin exception
        traceback.print_exc()
        return jsonify({"status": "error",
                        "message": "Selenium 처리 중 오류가 발생했습니다."}), 500

# ------------------------------------------------------------------------------------------------ Katri
def pdf_first_page_bytes_to_numpy(pdf_bytes: bytes, dpi: int = 300) -> np.ndarray:
    """바이트 버퍼로 받은 PDF 첫 페이지를 렌더링해 NumPy BGR 이미지 반환"""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page = doc.load_page(0)
        zoom = dpi / 72
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def read_qr_from_pdf_bytes(pdf_bytes: bytes, dpi: int = 300) -> str | None:
    cv_img = pdf_first_page_bytes_to_numpy(pdf_bytes, dpi)
    data, *_ = cv2.QRCodeDetector().detectAndDecode(cv_img)
    return data or None

@app.route("/katri", methods=["POST"])
def katri():
    file = request.files.get("pdf")
    if not file:
        return jsonify(error="pdf 파일을 첨부해 주세요."), 400

    # 1) 업로드된 PDF에서 QR 추출
    qr_text = read_qr_from_pdf_bytes(file.read())
    if not qr_text:
        return jsonify(error="QR을 인식하지 못했습니다."), 400

    parsed = urlparse(qr_text)
    if parsed.scheme not in ("http", "https"):
        return jsonify(error="QR 값이 URL 형식이 아닙니다."), 400

    try:
        # 2) Selenium으로 QR URL 접속
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        with webdriver.Chrome(options=options) as driver:
            wait = WebDriverWait(driver, 10)
            driver.get(qr_text)

            # (1) p.mt10.taC > a 대기
            link_elem = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "p.mt10.taC a"))
            )

            # (2) href 에서 goPDF 인자 추출
            href = link_elem.get_attribute("href") or ""
            print("HREF!!:",href)
            m = GO_PDF_RE.search(href)
            if not m:
                return jsonify(error="goPDF 링크를 파싱하지 못했습니다."), 404

            pdf_path = m.group(1)                                # '/mobile/pdfDownClient.do?...'
            # qr_text 의 scheme+netloc + pdf_path
            base = f"{parsed.scheme}://{parsed.netloc}"
            pdf_url = urljoin(base, pdf_path)

            # (3) Selenium 세션 쿠키 → requests(Session) 이식
            sess = requests.Session()
            for c in driver.get_cookies():
                sess.cookies.set(c["name"], c["value"])

        # 3) PDF 다운로드
        pdf_resp = sess.get(pdf_url, timeout=30, stream=True,
                            headers={"User-Agent": "Mozilla/5.0"})
        pdf_resp.raise_for_status()

        head = pdf_resp.raw.read(5)
        if head != b"%PDF-":
            return jsonify(error="다운로드한 파일이 PDF 형식이 아닙니다."), 502
        pdf_bytes = head + pdf_resp.raw.read()

        # 4) PDF → PNG 변환 & ZIP
        zip_buf = io.BytesIO()
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc, \
             zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:

            for idx in range(doc.page_count):
                pix = doc.load_page(idx).get_pixmap(alpha=False)
                zf.writestr(f"page_{idx+1}.png", pix.tobytes("png"))

        zip_buf.seek(0)
        return send_file(zip_buf,
                         as_attachment=True,
                         download_name="katri_pages.zip",
                         mimetype="application/zip")

    except TimeoutException:
        return jsonify(error="Selenium 대기 시간이 초과되었습니다."), 504
    except Exception:
        traceback.print_exc()
        return jsonify(error="PDF 다운로드/변환 중 오류가 발생했습니다."), 500


# ------------------------------------------------------------------------------------------------ Kotiti
@app.route("/kotiti", methods=["POST"])
def kotiti():
    file = request.files.get("pdf")
    if not file:
        return jsonify(error="pdf 파일을 첨부해 주세요."), 400

    # 1) 업로드 PDF → QR 텍스트 추출
    qr_text = read_qr_from_pdf_bytes(file.read())
    if not qr_text:
        return jsonify(error="QR을 인식하지 못했습니다."), 400

    parsed = urlparse(qr_text)
    if parsed.scheme not in ("http", "https"):
        return jsonify(error="QR 값이 URL 형식이 아닙니다."), 400

    try:
        # 2) PDF 직접 다운로드 (Selenium 불필요)
        resp = requests.get(qr_text, timeout=30, stream=True,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()

        head = resp.raw.read(5)
        if head != b"%PDF-":
            return jsonify(error="다운로드한 파일이 PDF 형식이 아닙니다."), 502
        pdf_bytes = head + resp.raw.read()

        # 3) PDF → PNG 변환 & ZIP
        zip_buf = io.BytesIO()
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc, \
             zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:

            for idx in range(doc.page_count):
                pix = doc.load_page(idx).get_pixmap(alpha=False)
                zf.writestr(f"page_{idx+1}.png", pix.tobytes("png"))

        zip_buf.seek(0)
        return send_file(zip_buf,
                         as_attachment=True,
                         download_name="kotiti_pages.zip",
                         mimetype="application/zip")

    except requests.Timeout:
        return jsonify(error="PDF 다운로드 시간이 초과되었습니다."), 504
    except Exception:
        traceback.print_exc()
        return jsonify(error="PDF 다운로드/변환 중 오류가 발생했습니다."), 500



if __name__ == "__main__":
    # reloader가 브라우저를 두 번 띄우는 현상 방지용 옵션
    app.run(host="0.0.0.0", port=8227, debug=True, use_reloader=False)
