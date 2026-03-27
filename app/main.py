"""入口：启动 Flask 网页版。"""

from app.web.routes import create_app

app = create_app()

if __name__ == "__main__":
    print("易经诊断工具启动中...")
    print("访问 http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
