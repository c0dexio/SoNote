from sonote.app import create_app

app = create_app()

if __name__ == "__main__":
    import threading
    import webbrowser
    threading.Timer(0.8, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
