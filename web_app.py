import re
from flask import Flask, jsonify, render_template
from stock_data import get_institutional, get_margin, get_stock_name

app = Flask(__name__)

_STOCK_RE = re.compile(r"^\d{4,6}$")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/name/<stock_id>")
def name_api(stock_id: str):
    if not _STOCK_RE.match(stock_id):
        return jsonify({"name": ""}), 400
    return jsonify({"name": get_stock_name(stock_id)})


@app.route("/api/stock/<stock_id>")
def stock_api(stock_id: str):
    if not _STOCK_RE.match(stock_id):
        return jsonify({"error": "無效的股票代號，請輸入 4~6 碼數字"}), 400
    try:
        inst   = get_institutional(stock_id, days=45)
        margin = get_margin(stock_id)
    except Exception as exc:
        return jsonify({"error": f"查詢失敗：{exc}"}), 500

    if not inst and not margin:
        return jsonify({"error": f"查無《{stock_id}》資料，請確認股票代號是否正確"}), 404

    return jsonify({"stock_id": stock_id, "institutional": inst, "margin": margin})


if __name__ == "__main__":
    app.run(debug=True, port=8080)
