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
import io, zipfile, time, traceback

app = Flask(__name__)

# Common Const
FITI_URL = "https://www.fiti.re.kr/cs/contents/CS0401010000.do"
PNG_SCROLL_DELAY = 0.3         

@app.route('/')
def health():
    return "server avaliable"

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



@app.route("/kotiti", methods=["POST"])
def kotiti():
    return "ok"


@app.route("/katri", methods=["POST"])
def katri():
    return "ok"



if __name__ == "__main__":
    # reloader가 브라우저를 두 번 띄우는 현상 방지용 옵션
    app.run(host="0.0.0.0", port=8227, debug=True, use_reloader=False)
